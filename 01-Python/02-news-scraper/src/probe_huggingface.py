"""
Probe: hit Hugging Face API, confirm data is reachable, print structure.
Not a scraper — just verification.
"""

import json
import requests

URL = "https://huggingface.co/api/models"
PARAMS = {
    "sort": "trendingScore",
    "direction": -1,
    "limit": 3,
}

print(f"→ GET {URL}")
print(f"  params: {PARAMS}\n")

resp = requests.get(URL, params=PARAMS, timeout=30)

print(f"status       : {resp.status_code}")
print(f"content-type : {resp.headers.get('content-type')}")
print(f"response size: {len(resp.text)} chars\n")

data = resp.json()
print(f"type         : {type(data).__name__}")
print(f"count        : {len(data)}\n")
print("=" * 70)

for i, model in enumerate(data, start=1):
    print(f"[{i}] id            : {model.get('id')}")
    print(f"    author        : {model.get('author')}")
    print(f"    downloads     : {model.get('downloads')}")
    print(f"    likes         : {model.get('likes')}")
    print(f"    pipeline_tag  : {model.get('pipeline_tag')}")
    print(f"    library_name  : {model.get('library_name')}")
    print(f"    createdAt     : {model.get('createdAt')}")
    print(f"    lastModified  : {model.get('lastModified')}")
    print(f"    tags          : {model.get('tags', [])[:10]}")
    print(f"    full keys     : {sorted(model.keys())}")
    print()