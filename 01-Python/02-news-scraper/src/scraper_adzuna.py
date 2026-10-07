"""
Adzuna India job scraper.

Searches Adzuna's India endpoint across multiple AI-relevant keywords
and stores the results as structured JSON.

Requires ADZUNA_APP_ID and ADZUNA_APP_KEY (read from .env or environment).

Usage:
    python scraper_adzuna.py
    python scraper_adzuna.py --audit
"""

import argparse
import json
import os
import re
import time
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse

import requests

# --- Load .env manually (no python-dotenv dependency) ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


APP_ID = os.getenv("ADZUNA_APP_ID", "")
APP_KEY = os.getenv("ADZUNA_APP_KEY", "")

DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_FILE = DATA_DIR / "adzuna.json"

API_BASE = "https://api.adzuna.com/v1/api/jobs/in/search"

SEARCH_TERMS = [
    "AI engineer",
    "machine learning engineer",
    "data scientist",
    "GenAI",
    "LLM engineer",
    "MLOps",
    "NLP engineer",
    "computer vision engineer",
    "data engineer",
    "AI research",
]

RESULTS_PER_PAGE = 50
MAX_PAGES_PER_TERM = 3
REQUEST_DELAY = 1.0


def load_json(path, default):
    if not path.exists():
        return deepcopy(default)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return deepcopy(default)


def save_json(path, data):
    temp_path = path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    temp_path.replace(path)


def normalize_url(url):
    if not url:
        return ""
    parsed = urlparse(url.strip())
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")


def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def merge_jobs(existing, new_jobs):
    by_url = {}
    for j in existing:
        u = normalize_url(j.get("url"))
        if u:
            by_url[u] = j
    for j in new_jobs:
        u = normalize_url(j.get("url"))
        if u:
            by_url[u] = j
    result = list(by_url.values())
    result.sort(key=lambda x: x.get("published_date") or "", reverse=True)
    return result


def fetch_page(term, page, retries=3):
    params = {
        "app_id": APP_ID,
        "app_key": APP_KEY,
        "results_per_page": RESULTS_PER_PAGE,
        "what": term,
        "content-type": "application/json",
        "sort_by": "date",
    }
    url = f"{API_BASE}/{page}"

    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            last_exc = exc
            time.sleep(2 * attempt)
    raise last_exc


def parse_job(raw):
    title = clean_text(raw.get("title") or "")
    if not title:
        return None

    company = clean_text((raw.get("company") or {}).get("display_name") or "")
    location = clean_text((raw.get("location") or {}).get("display_name") or "")
    description = clean_text(raw.get("description") or "")
    url = normalize_url(raw.get("redirect_url") or "")

    created = raw.get("created") or ""
    published = created[:10] if created else ""

    if not url or not published:
        return None

    salary_min = raw.get("salary_min")
    salary_max = raw.get("salary_max")
    salary_str = ""
    if salary_min and salary_max:
        salary_str = f"{int(salary_min)}-{int(salary_max)}"

    return {
        "title": title,
        "source": "Adzuna India",
        "url": url,
        "published_date": published,
        "content": f"{title}\n\nCompany: {company}\nLocation: {location}\n\n{description}",
        "company": company,
        "location": location,
        "salary": salary_str,
        "category": clean_text((raw.get("category") or {}).get("label") or ""),
    }


def run():
    if not APP_ID or not APP_KEY:
        print("ERROR: ADZUNA_APP_ID / ADZUNA_APP_KEY not set.")
        print("Create a .env file in the project root with:")
        print("  ADZUNA_APP_ID=...")
        print("  ADZUNA_APP_KEY=...")
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print()
    print("=" * 60)
    print("ADZUNA INDIA JOB SCRAPER")
    print("=" * 60)

    existing = load_json(OUTPUT_FILE, [])
    print(f"Existing jobs: {len(existing)}")
    print()

    all_jobs = []
    for term in SEARCH_TERMS:
        print(f"  [{term}]")
        for page in range(1, MAX_PAGES_PER_TERM + 1):
            try:
                data = fetch_page(term, page)
            except Exception as exc:
                print(f"    page {page} failed: {exc}")
                break

            results = data.get("results") or []
            if not results:
                break

            for raw in results:
                job = parse_job(raw)
                if job:
                    all_jobs.append(job)

            print(f"    page {page}: {len(results)} results")
            if len(results) < RESULTS_PER_PAGE:
                break
            time.sleep(REQUEST_DELAY)

    print()
    print(f"Fetched this run: {len(all_jobs)}")

    merged = merge_jobs(existing, all_jobs)
    save_json(OUTPUT_FILE, merged)

    print()
    print("=" * 60)
    print("RUN COMPLETE")
    print("=" * 60)
    print("New this run :", len(all_jobs))
    print("Total stored :", len(merged))
    print("Saved        :", OUTPUT_FILE)


def audit():
    data = load_json(OUTPUT_FILE, [])
    print()
    print("=" * 60)
    print("ADZUNA INDIA AUDIT")
    print("=" * 60)
    print("Jobs           :", len(data))
    if not data:
        return

    urls = [normalize_url(j.get("url")) for j in data]
    dates = sorted(j["published_date"] for j in data if j.get("published_date"))
    lengths = sorted(len(j.get("content", "")) for j in data)

    print("Unique URLs    :", len(set(urls)))
    if dates:
        print("Date range     :", dates[0], "->", dates[-1])
    print("Content len    : min", lengths[0],
          "| median", lengths[len(lengths) // 2],
          "| max", lengths[-1])

    loc_counter = {}
    for j in data:
        loc = j.get("location") or "Unknown"
        top = loc.split(",")[0].strip()
        loc_counter[top] = loc_counter.get(top, 0) + 1

    print()
    print("Top locations:")
    for loc, n in sorted(loc_counter.items(), key=lambda x: -x[1])[:10]:
        print(f"  {loc:<25s} : {n}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    if args.audit:
        audit()
    else:
        run()


if __name__ == "__main__":
    main()