"""
RAG Indexer — chunks + embeds enriched data into ChromaDB.

Sources indexed:
  - data/analytics_india_enriched.json  (AIM articles)
  - data/adzuna_enriched.json           (job listings)

Storage:
  - data/chroma_db/  (local persistent ChromaDB)

Embedding model: sentence-transformers/all-MiniLM-L6-v2 (local, free)

Usage:
    python rag_indexer.py            
    python rag_indexer.py --rebuild  # wipe and rebuild
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
CHROMA_DIR = DATA_DIR / "chroma_db"

EMBED_MODEL = "all-MiniLM-L6-v2"
COLLECTION_NAME = "career_intel"

# Truncate content so it fits within MiniLM's ~512 token limit
CONTENT_CHARS = 1500


def _make_id(*parts):
    """Stable short id from any strings."""
    h = hashlib.md5()
    for p in parts:
        h.update(str(p or "").encode("utf-8"))
    return h.hexdigest()[:16]


def _load_json(filename):
    path = DATA_DIR / filename
    if not path.exists():
        print(f"  skip: {filename} not found")
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def _build_document(record):
    """
    Compose the text that will be embedded.
    Combines title + summary + leading content.
    """
    title = (record.get("title") or "").strip()
    summary = (record.get("summary") or "").strip()
    content = (record.get("content") or "").strip()

    parts = [p for p in [title, summary, content[:CONTENT_CHARS]] if p]
    return "\n\n".join(parts)


def _prepare_articles():
    """AIM enriched articles → (ids, documents, metadatas)."""
    records = _load_json("analytics_india_enriched.json")
    ids, docs, metas = [], [], []
    for r in records:
        if r.get("_enrichment_error"):
            continue
        doc = _build_document(r)
        if not doc:
            continue
        url = (r.get("url") or "").strip()
        ids.append(_make_id("article", url))
        docs.append(doc)
        metas.append({
            "type": "article",
            "title": (r.get("title") or "")[:200],
            "source": r.get("source", "AIM"),
            "url": url,
            "date": r.get("published_date", ""),
            "category": r.get("category", ""),
        })
    return ids, docs, metas


def _prepare_jobs():
    """Adzuna enriched jobs → (ids, documents, metadatas)."""
    records = _load_json("adzuna_enriched.json")
    ids, docs, metas = [], [], []
    seen = set()
    for r in records:
        if r.get("_enrichment_error"):
            continue
        url = (r.get("url") or "").strip().rstrip("/")
        if not url or url in seen:
            continue
        seen.add(url)

        doc = _build_document(r)
        if not doc:
            continue

        ids.append(_make_id("job", url))
        docs.append(doc)
        metas.append({
            "type": "job",
            "title": (r.get("title") or "")[:200],
            "source": "Adzuna",
            "url": url,
            "date": r.get("published_date", ""),
            "company": (r.get("company") or "")[:100],
            "location": (r.get("location") or "")[:100],
        })
    return ids, docs, metas


def build(rebuild=False):
    print()
    print("=" * 60)
    print("RAG INDEXER")
    print("=" * 60)

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading embedding model: {EMBED_MODEL}")
    print("(first run downloads ~80 MB — one-time)")
    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBED_MODEL
    )

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    if rebuild:
        try:
            client.delete_collection(COLLECTION_NAME)
            print(f"Dropped existing collection: {COLLECTION_NAME}")
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )

    existing = collection.count()
    if existing and not rebuild:
        print(f"Collection already has {existing} documents. Skipping build.")
        print("Use --rebuild to force a rebuild.")
        return

    print("\nPreparing data...")
    a_ids, a_docs, a_metas = _prepare_articles()
    print(f"  AIM articles   : {len(a_ids)}")
    j_ids, j_docs, j_metas = _prepare_jobs()
    print(f"  Adzuna jobs    : {len(j_ids)}")

    all_ids = a_ids + j_ids
    all_docs = a_docs + j_docs
    all_metas = a_metas + j_metas
    print(f"  Total          : {len(all_ids)}")

    if not all_ids:
        print("Nothing to index.")
        return

    print("\nEmbedding + indexing (this takes 2-4 min on CPU)...")
    start = time.time()

    BATCH = 100
    for i in range(0, len(all_ids), BATCH):
        batch_ids = all_ids[i:i + BATCH]
        batch_docs = all_docs[i:i + BATCH]
        batch_metas = all_metas[i:i + BATCH]
        collection.add(ids=batch_ids, documents=batch_docs, metadatas=batch_metas)
        pct = min(100, int((i + BATCH) / len(all_ids) * 100))
        print(f"  indexed {min(i + BATCH, len(all_ids))}/{len(all_ids)}  ({pct}%)")

    elapsed = time.time() - start
    print()
    print("=" * 60)
    print("BUILD COMPLETE")
    print("=" * 60)
    print(f"Collection : {COLLECTION_NAME}")
    print(f"Documents  : {collection.count()}")
    print(f"Storage    : {CHROMA_DIR}")
    print(f"Time       : {elapsed:.1f}s")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild", action="store_true",
                        help="wipe existing collection and rebuild")
    args = parser.parse_args()
    build(rebuild=args.rebuild)


if __name__ == "__main__":
    main()