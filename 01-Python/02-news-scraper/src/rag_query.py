"""
RAG Query — fastembed + numpy (lightweight, cloud-safe).

Documents: pre-computed embeddings (numpy .npy in data/rag_store/).
Queries:   embedded on-the-fly via fastembed (ONNX, no torch).
Similarity: numpy cosine.

Usage:
    python rag_query.py "your question"
"""

import json
import os
import sys
from pathlib import Path

import numpy as np
from google import genai


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAG_DIR = DATA_DIR / "rag_store"
ENV_FILE = PROJECT_ROOT / ".env"

FASTEMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
GEMINI_MODEL = "gemini-flash-lite-latest"
TOP_K = 8
MAX_CONTEXT_CHARS = 8000


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


# ---------- Lazy loaders ----------
_EMBEDDINGS = None
_DOCS = None
_METAS = None
_EMBEDDER = None


def _load_store():
    global _EMBEDDINGS, _DOCS, _METAS
    if _EMBEDDINGS is not None:
        return
    emb_path = RAG_DIR / "embeddings.npy"
    docs_path = RAG_DIR / "docs.json"
    metas_path = RAG_DIR / "metas.json"
    if not emb_path.exists():
        raise RuntimeError(f"Embeddings not found at {emb_path}")
    _EMBEDDINGS = np.load(emb_path).astype(np.float32)
    with open(docs_path, "r", encoding="utf-8") as f:
        _DOCS = json.load(f)
    with open(metas_path, "r", encoding="utf-8") as f:
        _METAS = json.load(f)
    # L2 normalize once
    norms = np.linalg.norm(_EMBEDDINGS, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    _EMBEDDINGS = _EMBEDDINGS / norms


def _get_embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        from fastembed import TextEmbedding
        _EMBEDDER = TextEmbedding(model_name=FASTEMBED_MODEL)
    return _EMBEDDER


def _embed_query(text):
    embedder = _get_embedder()
    vecs = list(embedder.embed([text]))
    if not vecs:
        raise RuntimeError("fastembed returned no vectors")
    return np.array(vecs[0], dtype=np.float32)


def _cosine_top_k(query_vec, k):
    q = query_vec / (np.linalg.norm(query_vec) or 1.0)
    sims = _EMBEDDINGS @ q
    idx = np.argsort(-sims)[:k]
    return idx, sims[idx]


SYSTEM_PROMPT = (
    "You are an AI career intelligence assistant for the Indian AI/GenAI ecosystem. "
    "Answer questions using ONLY the provided context (news articles and job listings). "
    "If the context does not contain enough information, say so honestly — do not invent. "
    "Be concise. Cite sources when possible."
)

USER_TEMPLATE = """Context (relevant news articles and job listings):
{context}

Question: {question}

Answer based ONLY on the context above. If the context is insufficient, say so."""


def _format_context(indices, sims):
    blocks = []
    total = 0
    for rank, (i, sim) in enumerate(zip(indices, sims), start=1):
        doc = _DOCS[i]
        meta = _METAS[i]
        label = f"[{rank}] {meta.get('type', '?').upper()} | {meta.get('title', '')[:80]}"
        url = meta.get("url", "")
        block = f"{label}\n{'-' * 60}\n{doc}\nSource: {url}\n"
        total += len(block)
        if total > MAX_CONTEXT_CHARS:
            break
        blocks.append((block, meta))
    return "\n".join(b for b, _ in blocks), [m for _, m in blocks]


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
    if not question or not question.strip():
        return "Empty question.", []

    _load_store()

    try:
        qvec = _embed_query(question)
    except Exception as e:
        return f"[Embedding error: {e}]", []

    if qvec.shape[0] != _EMBEDDINGS.shape[1]:
        return (
            f"[Dim mismatch: query={qvec.shape[0]} docs={_EMBEDDINGS.shape[1]}. "
            f"Rebuild index with matching model.]",
            [],
        )

    idx, sims = _cosine_top_k(qvec, top_k)
    context_block, metas = _format_context(idx, sims)

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


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python rag_query.py "your question"')
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