# src/probe_hf_pagination.py
import requests

BASE = "https://huggingface.co/api/models"

for sort in ["trendingScore", "createdAt", "downloads"]:
    print(f"\n=== sort={sort} ===")
    for start in [0, 1000]:
        r = requests.get(BASE, params={
            "sort": sort, "direction": -1, "limit": 100, "start": start,
        }, timeout=30)
        data = r.json()
        first_id = data[0]["id"] if data else "NONE"
        print(f"  start={start:>5} | got={len(data):>4} | first_id={first_id}")