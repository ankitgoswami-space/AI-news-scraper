"""
RemoteOK scraper.

Public JSON API at https://remoteok.com/api — no auth.
Returns the current remote-jobs listing (~99 jobs).

Usage:
    python scraper_remoteok.py
    python scraper_remoteok.py --audit
"""

import argparse
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import requests


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "remoteok.json"

API_URL = "https://remoteok.com/api"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept": "application/json"}


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


def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_job(raw):
    if not isinstance(raw, dict):
        return None
    job_id = raw.get("id")
    position = clean_text(raw.get("position") or "")
    if not job_id or not position:
        return None

    url = f"https://remoteok.com/remote-jobs/{job_id}"
    company = clean_text(raw.get("company") or "")
    location = clean_text(raw.get("location") or "")
    tags = raw.get("tags") or []
    description = clean_text(raw.get("description") or "")

    epoch = raw.get("epoch")
    published = ""
    if epoch:
        published = datetime.fromtimestamp(epoch, tz=timezone.utc).date().isoformat()

    if not published:
        return None

    return {
        "title": position,
        "source": "RemoteOK",
        "url": url,
        "published_date": published,
        "content": f"{position}\n\nCompany: {company}\nLocation: {location}\nTags: {', '.join(tags)}\n\n{description}",
        "company": company,
        "location": location,
        "tags": tags,
    }


def merge_jobs(existing, new_jobs):
    by_url = {}
    for j in existing:
        by_url[j.get("url")] = j
    for j in new_jobs:
        by_url[j.get("url")] = j
    return sorted(by_url.values(), key=lambda x: x.get("published_date") or "", reverse=True)


def run():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print()
    print("=" * 60)
    print("REMOTEOK SCRAPER")
    print("=" * 60)

    r = requests.get(API_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()

    raw_jobs = [x for x in data if isinstance(x, dict) and x.get("id")]
    print(f"Raw entries from API: {len(raw_jobs)}")

    new_jobs = [parse_job(x) for x in raw_jobs]
    new_jobs = [j for j in new_jobs if j]

    existing = load_json(OUTPUT_FILE, [])
    merged = merge_jobs(existing, new_jobs)
    save_json(OUTPUT_FILE, merged)

    print()
    print("=" * 60)
    print("RUN COMPLETE")
    print("=" * 60)
    print("New this run :", len(new_jobs))
    print("Total stored :", len(merged))
    print("Saved        :", OUTPUT_FILE)


def audit():
    data = load_json(OUTPUT_FILE, [])
    print()
    print("=" * 60)
    print("REMOTEOK AUDIT")
    print("=" * 60)
    print("Jobs           :", len(data))
    if not data:
        return

    dates = sorted(j["published_date"] for j in data if j.get("published_date"))
    lengths = sorted(len(j.get("content", "")) for j in data)
    if dates:
        print("Date range     :", dates[0], "->", dates[-1])
    print("Content len    : min", lengths[0],
          "| median", lengths[len(lengths) // 2],
          "| max", lengths[-1])

    tag_counter = {}
    for j in data:
        for t in j.get("tags") or []:
            tag_counter[t] = tag_counter.get(t, 0) + 1
    print()
    print("Top tags:")
    for t, n in sorted(tag_counter.items(), key=lambda x: -x[1])[:15]:
        print(f"  {t:<25s} : {n}")


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