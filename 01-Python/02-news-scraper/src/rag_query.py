"""
RAG Query — retrieve relevant chunks + generate grounded answer via Gemini.

Usage (CLI):
    python rag_query.py "Kaunsi Indian startups RAG pe kaam kar rahi hain?"
"""

import os
import sys
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from google import genai


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CHROMA_DIR = DATA_DIR / "chroma_db"
ENV_FILE = PROJECT_ROOT / ".env"

EMBED_MODEL = "all-MiniLM-L6-v2"
COLLECTION_NAME = "career_intel"
GEMINI_MODEL = "gemini-flash-lite-latest"

TOP_K = 8                    # how many chunks to retrieve
MAX_CONTEXT_CHARS = 8000     # cap prompt size


# ---------- Load env ----------
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

_gemini_key = os.getenv("GEMINI_API_KEY", "")
_client = genai.Client(api_key=_gemini_key) if _gemini_key else None


# ---------- Chroma ----------
_embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name=EMBED_MODEL
)
_chroma = chromadb.PersistentClient(path=str(CHROMA_DIR))
_collection = _chroma.get_or_create_collection(
    name=COLLECTION_NAME,
    embedding_function=_embedding_fn,
)


SYSTEM_PROMPT = (
    "You are an AI career intelligence assistant for the Indian AI/GenAI ecosystem. "
    "You answer questions using ONLY the provided context (news articles and job listings). "
    "If the context does not contain enough information, say so honestly — do not invent. "
    "Be concise. Cite sources when possible."
)

USER_TEMPLATE = """Context (relevant news articles and job listings):
{context}

Question: {question}

Answer based ONLY on the context above. If the context is insufficient, say so."""


def _format_context(results):
    """Turn ChromaDB results into a numbered context block."""
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    blocks = []
    total = 0
    for i, (doc, meta, dist) in enumerate(zip(docs, metas, distances), start=1):
        # Distance → relevance (cosine: smaller = better)
        relevance = max(0.0, 1.0 - float(dist))
        label = f"[{i}] {meta.get('type', '?').upper()} | {meta.get('title', '')[:80]}"
        url = meta.get("url", "")
        block = f"{label}\n{'-' * 60}\n{doc}\nSource: {url}\n"
        total += len(block)
        if total > MAX_CONTEXT_CHARS:
            break
        blocks.append(block)

    return "\n".join(blocks), [m for m in metas[:len(blocks)]]


def _ask_gemini(prompt):
    if _client is None:
        raise RuntimeError("GEMINI_API_KEY not set in .env")

    resp = _client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config={"temperature": 0.2},
    )
    return resp.text


def query(question, top_k=TOP_K, return_sources=True):
    """
    Returns (answer, sources) where sources is a list of
    {title, url, type, relevance} dicts.
    """
    if not question or not question.strip():
        return "Empty question.", []

    results = _collection.query(
        query_texts=[question],
        n_results=top_k,
    )

    if not results.get("documents") or not results["documents"][0]:
        return "No relevant information found in the knowledge base.", []

    context_block, metas = _format_context(results)
    prompt = SYSTEM_PROMPT + "\n\n" + USER_TEMPLATE.format(
        context=context_block,
        question=question,
    )

    try:
        answer = _ask_gemini(prompt)
    except Exception as exc:
        answer = f"[LLM error: {exc}]"
        metas = []

    if not return_sources:
        return answer, []

    sources = []
    for m in metas:
        sources.append({
            "type": m.get("type", ""),
            "title": m.get("title", ""),
            "url": m.get("url", ""),
            "company": m.get("company", ""),
            "location": m.get("location", ""),
            "date": m.get("date", ""),
        })

    return answer, sources


# ---------- CLI ----------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python rag_query.py \"your question\"")
        sys.exit(1)

    question = " ".join(sys.argv[1:])
    print(f"\nQ: {question}\n")
    answer, sources = query(question)
    print("A:", answer)
    if sources:
        print("\nSources:")
        for s in sources:
            tag = s["type"].upper()
            extra = ""
            if s["type"] == "job":
                extra = f" — {s['company']} ({s['location']})"
            print(f"  [{tag}] {s['title'][:80]}{extra}")
            if s["url"]:
                print(f"         {s['url']}")
    print()