"""
We Work Remotely RSS scraper.

Uses the public programming-jobs RSS feed. No auth.

Usage:
    python scraper_wwr.py
    python scraper_wwr.py --audit
"""

import argparse
import json
import re
from copy import deepcopy
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "wwr.json"

FEED_URL = "https://weworkremotely.com/categories/remote-programming-jobs.rss"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept": "application/rss+xml,application/xml;q=0.9,*/*;q=0.8"}


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
    if "<" in text:
        text = BeautifulSoup(text, "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", text).strip()


def parse_date(value):
    if not value:
        return None
    try:
        return parsedate_to_datetime(str(value).strip()).date()
    except Exception:
        return None


def parse_item(item):
    title_el = item.find("title")
    link_el = item.find("link")
    date_el = item.find("pubDate")
    desc_el = item.find("description")

    title = clean_text(title_el.get_text()) if title_el else ""
    link = link_el.get_text(strip=True) if link_el else ""
    date_str = date_el.get_text(strip=True) if date_el else ""
    desc = clean_text(desc_el.get_text()) if desc_el else ""

    published = parse_date(date_str)
    if not (title and link and published):
        return None

    return {
        "title": title,
        "source": "We Work Remotely",
        "url": link,
        "published_date": published.isoformat(),
        "content": f"{title}\n\n{desc}",
        "company": title.split(":")[0].strip() if ":" in title else "",
        "location": "Remote",
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
    print("WE WORK REMOTELY SCRAPER")
    print("=" * 60)

    r = requests.get(FEED_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "xml")
    items = soup.find_all("item")
    print(f"Items in feed: {len(items)}")

    new_jobs = [parse_item(i) for i in items]
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
    print("WWR AUDIT")
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