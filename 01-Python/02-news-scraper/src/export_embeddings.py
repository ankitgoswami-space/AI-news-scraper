"""
Export ChromaDB collection to NumPy format for lightweight deployment.

Outputs (in data/rag_store/):
  - embeddings.npy  (N x 384 float32)
  - docs.json       (list of N text chunks)
  - metas.json      (list of N metadata dicts)

Usage:
    python export_embeddings.py
"""

import json
from pathlib import Path

import numpy as np
import chromadb
from chromadb.utils import embedding_functions


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHROMA_DIR = PROJECT_ROOT / "data" / "chroma_db"
OUT_DIR = PROJECT_ROOT / "data" / "rag_store"
COLLECTION_NAME = "career_intel"

OUT_DIR.mkdir(parents=True, exist_ok=True)

print("Connecting to ChromaDB...")
client = chromadb.PersistentClient(path=str(CHROMA_DIR))
collection = client.get_collection(name=COLLECTION_NAME)

print(f"Reading {collection.count()} documents...")
data = collection.get(include=["embeddings", "documents", "metadatas"])

embeddings = np.array(data["embeddings"], dtype=np.float32)
docs = data["documents"]
metas = data["metadatas"]

print(f"  embeddings shape: {embeddings.shape}")
print(f"  docs            : {len(docs)}")
print(f"  metas           : {len(metas)}")

# Save
np.save(OUT_DIR / "embeddings.npy", embeddings)
with open(OUT_DIR / "docs.json", "w", encoding="utf-8") as f:
    json.dump(docs, f, ensure_ascii=False)
with open(OUT_DIR / "metas.json", "w", encoding="utf-8") as f:
    json.dump(metas, f, ensure_ascii=False)

print(f"\nSaved to {OUT_DIR}")
print(f"  embeddings.npy  ({embeddings.nbytes / 1024 / 1024:.1f} MB)")
print(f"  docs.json")
print(f"  metas.json")