"""
arXiv scraper (Atom API -> clean article JSON)

Usage:
    python scraper_12_arxiv.py                  # default: last 30 days
    python scraper_12_arxiv.py --days 90        # last 90 days
    python scraper_12_arxiv.py --incremental    # since last stored date
    python scraper_12_arxiv.py --audit          # quality report, no fetching
"""

import argparse
import json
import logging
import re
import time
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIG
# ============================================================

SOURCE_NAME = "arXiv"
API_URL = "http://export.arxiv.org/api/query"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

OUTPUT_FILE = DATA_DIR / "arxiv.json"
STATE_FILE = DATA_DIR / "arxiv_state.json"
LOG_FILE = DATA_DIR / "arxiv.log"

# AI career-relevant categories on arXiv
CATEGORIES = ["cs.AI", "cs.CL", "cs.LG"]

DEFAULT_DAYS = 30
PAGE_SIZE = 100           # arXiv max per request
REQUEST_DELAY = 3.0       # arXiv polite delay between requests
MAX_RETRIES = 3

MIN_CONTENT_CHARS = 50    # abstracts are short; a summary under 50 is useless

USER_AGENT = (
    "AI-Career-Intel-Project/0.1 "
    "(educational research; https://github.com/ankitgoswami-space/AI-news-scraper)"
)


# ============================================================
# LOGGING
# ============================================================

DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


# ============================================================
# HTTP SESSION
# ============================================================

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept": "application/atom+xml,application/xml;q=0.9,*/*;q=0.8",
    }
)


# ============================================================
# BASIC HELPERS
# ============================================================

def normalize_arxiv_url(url):
    """
    arXiv article URLs look like:
        http://arxiv.org/abs/2610.03717v1
        https://arxiv.org/abs/2610.03717v2
    We want a stable canonical form without the version:
        https://arxiv.org/abs/2610.03717
    """
    if not url:
        return ""

    parsed = urlparse(url.strip())
    path = parsed.path.rstrip("/")

    # strip trailing vN (e.g. /abs/2610.03717v1 -> /abs/2610.03717)
    path = re.sub(r"v\d+$", "", path)

    return f"https://arxiv.org{path}"


def clean_text(text):
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_date_string(value):
    """arXiv gives ISO timestamps like '2026-10-02T17:59:14Z'."""
    if not value:
        return None
    value = str(value).strip()

    match = re.search(r"(20\d{2})-(\d{1,2})-(\d{1,2})", value)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass
    return None


# ============================================================
# JSON HELPERS
# ============================================================

def load_json(path, default):
    if not path.exists():
        return deepcopy(default)
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as exc:
        logger.error("Could not read %s: %s", path, exc)
        return deepcopy(default)


def save_json(path, data):
    temp_path = path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    temp_path.replace(path)


# ============================================================
# STATE
# ============================================================

DEFAULT_STATE = {
    "last_run": None,
    "last_published_date": None,
}


def load_state():
    state = deepcopy(DEFAULT_STATE)
    loaded = load_json(STATE_FILE, {})
    if isinstance(loaded, dict):
        state.update(loaded)
    return state


def save_state(state):
    state["last_run"] = datetime.now().isoformat(timespec="seconds")
    save_json(STATE_FILE, state)


# ============================================================
# EXISTING DATA
# ============================================================

def load_existing_articles():
    data = load_json(OUTPUT_FILE, [])
    return data if isinstance(data, list) else []


def merge_articles(existing, new_articles):
    """Merge by normalized URL. Newer record replaces older one."""
    by_url = {}

    for article in existing:
        url = normalize_arxiv_url(article.get("url"))
        if url:
            by_url[url] = article

    for article in new_articles:
        url = normalize_arxiv_url(article.get("url"))
        if not url:
            continue
        by_url[url] = article

    result = list(by_url.values())
    result.sort(
        key=lambda item: item.get("published_date") or "",
        reverse=True,
    )
    return result


# ============================================================
# QUERY BUILDER
# ============================================================

def build_query(categories, start_date, end_date):
    """
    Build an arXiv search query for the given categories and date range.
        (cat:cs.AI OR cat:cs.CL OR cat:cs.LG)
            AND submittedDate:[202609010000 TO 202610050000]
    """
    cat_clause = " OR ".join(f"cat:{c}" for c in categories)
    date_clause = (
        f"submittedDate:[{start_date:%Y%m%d%H%M} "
        f"TO {end_date:%Y%m%d%H%M}]"
    )
    return f"({cat_clause}) AND {date_clause}"


# ============================================================
# FETCH
# ============================================================

def fetch_page(query, start, page_size, retries=MAX_RETRIES):
    """Fetch one page of results. Retries on network / 5xx errors."""
    params = {
        "search_query": query,
        "start": start,
        "max_results": page_size,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            resp = SESSION.get(API_URL, params=params, timeout=30)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            last_exc = exc
            logger.warning("arXiv fetch failed (%s/%s): %s", attempt, retries, exc)
            time.sleep(3 * attempt)

    raise last_exc


# ============================================================
# PARSE
# ============================================================

def parse_entries(xml_text):
    """Parse an arXiv Atom response into a list of article dicts."""
    soup = BeautifulSoup(xml_text, "xml")
    articles = []

    for entry in soup.find_all("entry"):
        try:
            title_el = entry.find("title")
            id_el = entry.find("id")
            published_el = entry.find("published")
            summary_el = entry.find("summary")

            if not (title_el and id_el and published_el and summary_el):
                continue

            title = clean_text(title_el.get_text())
            url = normalize_arxiv_url(id_el.get_text(strip=True))
            published = parse_date_string(published_el.get_text(strip=True))
            summary = clean_text(summary_el.get_text())

            if not title or not url or not published:
                continue

            if len(summary) < MIN_CONTENT_CHARS:
                continue

            authors = [
                clean_text(a.find("name").get_text())
                for a in entry.find_all("author")
                if a.find("name")
            ]

            categories = [
                c.get("term")
                for c in entry.find_all("category")
                if c.get("term")
            ]

            primary_el = entry.find("primary_category")
            primary_category = (
                primary_el.get("term")
                if primary_el and primary_el.get("term")
                else (categories[0] if categories else "")
            )

            articles.append(
                {
                    "title": title,
                    "source": SOURCE_NAME,
                    "url": url,
                    "published_date": published.isoformat(),
                    "content": summary,
                    "authors": authors,
                    "categories": categories,
                    "primary_category": primary_category,
                }
            )
        except Exception as exc:
            logger.warning("Skipping malformed entry: %s", exc)
            continue

    return articles


# ============================================================
# DATE WINDOWS
# ============================================================

def week_windows(start_date, end_date):
    """
    Yield (window_start, window_end) pairs, one per 7-day chunk.
    Chunking keeps each query under arXiv's ~3000-result pagination
    ceiling, and keeps individual responses small.
    """
    current = start_date
    while current < end_date:
        window_end = min(current + timedelta(days=7), end_date)
        yield current, window_end
        current = window_end


# ============================================================
# FETCH ALL
# ============================================================

def fetch_all(start_date, end_date, max_total=0):
    """
    Fetch all papers in the date range, chunked by week.
    Returns a list of article dicts.
    """
    all_articles = []
    seen_urls = set()

    windows = list(week_windows(start_date, end_date))
    print(f"Date range   : {start_date} -> {end_date}")
    print(f"Windows      : {len(windows)} weeks")
    print(f"Categories   : {', '.join(CATEGORIES)}")
    print()

    for i, (w_start, w_end) in enumerate(windows, start=1):
        query = build_query(CATEGORIES, w_start, w_end)
        print(f"[{i}/{len(windows)}] week {w_start} -> {w_end}")

        start = 0
        window_count = 0

        while True:
            try:
                xml_text = fetch_page(query, start, PAGE_SIZE)
            except Exception as exc:
                print(f"      fetch failed: {exc}")
                logger.error("Fetch failed for window %s-%s: %s", w_start, w_end, exc)
                break

            articles = parse_entries(xml_text)

            if not articles:
                break

            fresh = 0
            for art in articles:
                if art["url"] in seen_urls:
                    continue
                seen_urls.add(art["url"])
                all_articles.append(art)
                fresh += 1

            window_count += len(articles)
            print(f"      page start={start} | entries={len(articles)} | new={fresh}")

            if len(articles) < PAGE_SIZE:
                break

            start += PAGE_SIZE

            if max_total and len(all_articles) >= max_total:
                print(f"      reached max_total ({max_total}), stopping")
                break

            time.sleep(REQUEST_DELAY)

        if max_total and len(all_articles) >= max_total:
            break

        time.sleep(REQUEST_DELAY)

    return all_articles


# ============================================================
# AUDIT
# ============================================================

def audit():
    articles = load_existing_articles()

    print()
    print("=" * 60)
    print("ARXIV CONTENT AUDIT")
    print("=" * 60)

    if not articles:
        print("No articles stored yet.")
        return

    lengths = sorted(len(a.get("content", "")) for a in articles)
    dates = sorted(a["published_date"] for a in articles if a.get("published_date"))
    urls = [normalize_arxiv_url(a.get("url")) for a in articles]
    cats = {}
    for a in articles:
        for c in a.get("categories", []):
            cats[c] = cats.get(c, 0) + 1

    print("Articles           :", len(articles))
    print("Unique URLs        :", len(set(urls)))
    print("Missing date       :", len(articles) - len(dates))
    if dates:
        print("Date range         :", dates[0], "->", dates[-1])
    print("Content length     : min", lengths[0],
          "| median", lengths[len(lengths) // 2], "| max", lengths[-1])

    print()
    print("Top categories:")
    for cat, n in sorted(cats.items(), key=lambda x: -x[1])[:10]:
        print(f"  {cat:10s} : {n}")


# ============================================================
# RUN
# ============================================================

def run(args):
    print()
    print("=" * 60)
    print("ARXIV SCRAPER")
    print("=" * 60)

    state = load_state()
    today = date.today()

    if args.incremental:
        last = state.get("last_published_date")
        if last:
            start_date = parse_date_string(last)
            print(f"MODE: INCREMENTAL (since {start_date})")
        else:
            start_date = today - timedelta(days=DEFAULT_DAYS)
            print(f"MODE: INCREMENTAL, no prior state -> last {DEFAULT_DAYS} days")
    else:
        start_date = today - timedelta(days=args.days)
        print(f"MODE: BACKFILL (last {args.days} days)")

    end_date = today

    existing = load_existing_articles()
    print(f"Existing articles: {len(existing)}")

    new_articles = fetch_all(start_date, end_date, max_total=args.max_results)

    print()
    print(f"Fetched this run: {len(new_articles)}")

    merged = merge_articles(existing, new_articles)
    save_json(OUTPUT_FILE, merged)

    if new_articles:
        newest = max(a["published_date"] for a in new_articles)
        state["last_published_date"] = newest
        save_state(state)

    print()
    print("=" * 60)
    print("RUN COMPLETE")
    print("=" * 60)
    print("New this run     :", len(new_articles))
    print("Total stored     :", len(merged))
    print("Last published   :", state.get("last_published_date"))
    print()
    print("Saved:", OUTPUT_FILE)


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="arXiv scraper")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS,
                        help=f"how many days back to fetch (default {DEFAULT_DAYS})")
    parser.add_argument("--incremental", action="store_true",
                        help="fetch only since the last stored published date")
    parser.add_argument("--max-results", type=int, default=0,
                        help="cap total results this run (0 = unlimited)")
    parser.add_argument("--audit", action="store_true",
                        help="print a quality report and exit")
    args = parser.parse_args()

    if args.audit:
        audit()
        return

    run(args)


if __name__ == "__main__":
    main()