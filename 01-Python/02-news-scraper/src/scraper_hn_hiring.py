"""
Hacker News 'Who is Hiring?' scraper.

Fetches the latest monthly thread from HN's whoishiring user, then pulls
every top-level comment (each is a job posting).

No auth required. Uses the public Firebase HN API.

Usage:
    python scraper_hn_hiring.py
    python scraper_hn_hiring.py --audit
"""

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "hn_hiring.json"

HN_API = "https://hacker-news.firebaseio.com/v0"
REQUEST_DELAY = 0.3


# ============================================================
# HELPERS
# ============================================================

def load_json(path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    temp_path = path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    temp_path.replace(path)


def html_to_text(html):
    if not html:
        return ""
    text = re.sub(r"<p>", "\n\n", html)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&#x27;", "'").replace("&quot;", '"')
    text = text.replace("&amp;", "&").replace("&gt;", ">").replace("&lt;", "<")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def detect_location(text):
    text_lower = text.lower()
    india_cities = [
        "bengaluru", "bangalore", "hyderabad", "gurgaon", "gurugram",
        "noida", "mumbai", "pune", "chennai", "delhi", "new delhi",
        "kolkata", "ahmedabad", "jaipur", "kochi", "trivandrum",
    ]
    for city in india_cities:
        if city in text_lower:
            return city.title()
    if "india" in text_lower:
        return "India"
    if "remote" in text_lower:
        return "Remote"
    return ""


# ============================================================
# FETCH
# ============================================================

def get_latest_hiring_thread_id():
    r = requests.get(f"{HN_API}/user/whoishiring.json", timeout=20)
    r.raise_for_status()
    submitted = r.json().get("submitted", [])[:20]

    for item_id in submitted:
        time.sleep(REQUEST_DELAY)
        item_r = requests.get(f"{HN_API}/item/{item_id}.json", timeout=20)
        item = item_r.json()
        title = (item.get("title") or "").lower()
        if "who is hiring" in title and "ask hn" in title:
            return item_id, item.get("title"), item.get("time")

    return None, None, None


def fetch_comment(comment_id):
    r = requests.get(f"{HN_API}/item/{comment_id}.json", timeout=20)
    r.raise_for_status()
    return r.json()


# ============================================================
# PARSE
# ============================================================

def parse_job_post(item):
    if not item or item.get("deleted") or item.get("dead"):
        return None

    text = html_to_text(item.get("text") or "")
    if len(text) < 100:
        return None

    first_line = text.split("\n")[0].strip()
    parts = [p.strip() for p in first_line.split("|")]
    company = parts[0] if parts else ""
    role = parts[1] if len(parts) > 1 else ""

    return {
        "title": f"{company} — {role}" if company and role else first_line[:150],
        "source": "HN Who's Hiring",
        "url": f"https://news.ycombinator.com/item?id={item['id']}",
        "published_date": datetime.fromtimestamp(item["time"], tz=timezone.utc).date().isoformat(),
        "content": text,
        "company": company,
        "location": detect_location(text),
    }


# ============================================================
# MAIN
# ============================================================

def run():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print()
    print("=" * 60)
    print("HN WHO'S HIRING SCRAPER")
    print("=" * 60)

    thread_id, thread_title, thread_time = get_latest_hiring_thread_id()
    if not thread_id:
        print("Could not find latest hiring thread.")
        return

    print(f"Thread: {thread_title}")
    print(f"ID    : {thread_id}")

    thread_r = requests.get(f"{HN_API}/item/{thread_id}.json", timeout=20)
    thread = thread_r.json()
    kids = thread.get("kids", [])
    print(f"Top-level comments: {len(kids)}")
    print()
    print("Fetching each comment...")

    jobs = []
    for i, kid_id in enumerate(kids, start=1):
        try:
            item = fetch_comment(kid_id)
            job = parse_job_post(item)
            if job:
                jobs.append(job)
                if i % 25 == 0:
                    print(f"  [{i}/{len(kids)}] parsed {len(jobs)} jobs so far")
        except Exception as exc:
            print(f"  [{i}] failed: {exc}")
        time.sleep(REQUEST_DELAY)

    print()
    print(f"Parsed total: {len(jobs)} job posts")

    existing = load_json(OUTPUT_FILE, [])
    by_url = {a["url"]: a for a in existing}
    for j in jobs:
        by_url[j["url"]] = j
    merged = list(by_url.values())
    merged.sort(key=lambda x: x.get("published_date") or "", reverse=True)
    save_json(OUTPUT_FILE, merged)

    print(f"Total stored: {len(merged)}")
    print(f"Saved       : {OUTPUT_FILE}")


def audit():
    data = load_json(OUTPUT_FILE, [])
    print()
    print("=" * 60)
    print("HN WHO'S HIRING AUDIT")
    print("=" * 60)
    print("Jobs           :", len(data))
    if data:
        dates = sorted(d["published_date"] for d in data if d.get("published_date"))
        if dates:
            print("Date range     :", dates[0], "->", dates[-1])
        lengths = sorted(len(d.get("content", "")) for d in data)
        print("Content len    : min", lengths[0],
              "| median", lengths[len(lengths) // 2],
              "| max", lengths[-1])

        india = sum(1 for d in data if d.get("location") in {
            "Bengaluru", "Bangalore", "Hyderabad", "Gurgaon", "Gurugram",
            "Noida", "Mumbai", "Pune", "Chennai", "Delhi", "New Delhi",
            "Kolkata", "Ahmedabad", "Jaipur", "Kochi", "Trivandrum", "India",
        })
        print(f"India-tagged   : {india}")


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