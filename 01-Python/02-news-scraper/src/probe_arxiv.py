"""
Probe: hit arXiv API, confirm data is reachable, print structure.
Not a scraper — just verification.
"""

import requests
from bs4 import BeautifulSoup

URL = "http://export.arxiv.org/api/query"
PARAMS = {
    "search_query": "cat:cs.AI",
    "start": 0,
    "max_results": 3,
    "sortBy": "submittedDate",
    "sortOrder": "descending",
}

print(f"→ GET {URL}")
print(f"  params: {PARAMS}\n")

resp = requests.get(URL, params=PARAMS, timeout=30)

print(f"status: {resp.status_code}")
print(f"content-type: {resp.headers.get('content-type')}")
print(f"response size: {len(resp.text)} chars\n")

soup = BeautifulSoup(resp.text, "xml")
entries = soup.find_all("entry")

print(f"entries found: {len(entries)}\n")
print("=" * 70)

for i, entry in enumerate(entries, start=1):
    title = entry.find("title").get_text(strip=True)
    published = entry.find("published").get_text(strip=True)
    link = entry.find("id").get_text(strip=True)
    summary = entry.find("summary").get_text(strip=True)[:200]

    authors = [a.find("name").get_text(strip=True) for a in entry.find_all("author")]
    categories = [c.get("term") for c in entry.find_all("category")]

    print(f"[{i}] {title}")
    print(f"    published : {published}")
    print(f"    url       : {link}")
    print(f"    authors   : {authors}")
    print(f"    categories: {categories}")
    print(f"    summary   : {summary}...")
    print()