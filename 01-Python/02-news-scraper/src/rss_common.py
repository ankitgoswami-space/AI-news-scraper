"""
Shared RSS scraper utilities.

Each RSS-based source is a thin wrapper that defines a CONFIG dict and
calls main_for(CONFIG). All fetch / parse / merge / save logic lives here.

Some feeds return only a short teaser in their <description> — for those,
set `fetch_full_content: True` and provide `content_selectors` to extract
the full article body from the page HTML.
"""

import argparse
import json
import logging
import re
import time
from copy import deepcopy
from datetime import date
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
FULL_CONTENT_DELAY = 1.0        # seconds between article fetches
MIN_FULL_CONTENT_CHARS = 500    # below this, keep the RSS teaser instead


# ============================================================
# BASIC HELPERS
# ============================================================

def normalize_url(url):
    if not url:
        return ""
    parsed = urlparse(url.strip())
    clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    return clean.rstrip("/")


def clean_text(text):
    if not text:
        return ""
    if "<" in text:
        text = BeautifulSoup(text, "html.parser").get_text(" ")
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_rss_date(value):
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(str(value).strip())
        return dt.date()
    except Exception:
        match = re.search(r"(20\d{2})-(\d{1,2})-(\d{1,2})", str(value))
        if match:
            try:
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                pass
    return None


# ============================================================
# JSON
# ============================================================

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


def load_existing(path):
    data = load_json(path, [])
    return data if isinstance(data, list) else []


def merge_articles(existing, new_articles):
    by_url = {}
    for a in existing:
        u = normalize_url(a.get("url"))
        if u:
            by_url[u] = a
    for a in new_articles:
        u = normalize_url(a.get("url"))
        if u:
            by_url[u] = a
    result = list(by_url.values())
    # Drop articles with no usable content at all.
    result = [a for a in result if len(a.get("content", "")) > 0]
    result.sort(key=lambda x: x.get("published_date") or "", reverse=True)
    return result


# ============================================================
# LOGGING
# ============================================================

def build_logger(name, log_path):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(handler)
    return logger


# ============================================================
# FETCH
# ============================================================

def fetch_url(url, retries=MAX_RETRIES):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/rss+xml,application/atom+xml,"
                  "application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT,
                                allow_redirects=True)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            last_exc = exc
            time.sleep(2 * attempt)
    raise last_exc


# ============================================================
# PARSE RSS
# ============================================================

def parse_rss_items(xml_text, source_name):
    soup = BeautifulSoup(xml_text, "xml")
    items = soup.find_all("item") or soup.find_all("entry")

    articles = []
    for item in items:
        try:
            title_el = item.find("title")
            if not title_el:
                continue
            title = clean_text(title_el.get_text())
            if not title:
                continue

            link_el = item.find("link")
            link = ""
            if link_el:
                link = link_el.get_text(strip=True) or link_el.get("href", "")
            link = normalize_url(link)
            if not link:
                continue

            date_el = (
                item.find("pubDate")
                or item.find("published")
                or item.find("updated")
            )
            date_str = date_el.get_text(strip=True) if date_el else ""
            published = parse_rss_date(date_str)
            if not published:
                continue

            content_el = (
                item.find("encoded")
                or item.find("content:encoded")
                or item.find("description")
                or item.find("summary")
            )
            content = ""
            if content_el:
                content = clean_text(content_el.get_text())

            articles.append(
                {
                    "title": title,
                    "source": source_name,
                    "url": link,
                    "published_date": published.isoformat(),
                    "content": content,
                }
            )
        except Exception:
            continue

    return articles


# ============================================================
# FULL CONTENT EXTRACTION
# ============================================================

def extract_full_content(html, selectors):
    """
    Try each CSS selector in order; return the longest text found
    that clears MIN_FULL_CONTENT_CHARS. Returns "" if none qualify.
    """
    soup = BeautifulSoup(html, "html.parser")

    best = ""
    for sel in selectors:
        el = soup.select_one(sel)
        if not el:
            continue
        text = el.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > len(best):
            best = text

    return best if len(best) >= MIN_FULL_CONTENT_CHARS else ""


def enrich_with_full_content(articles, config, logger):
    """
    For each article, fetch its URL and replace the RSS teaser with the
    extracted full body. On failure, keep the teaser (never worse off).
    """
    selectors = config.get("content_selectors") or []
    if not selectors:
        return articles

    total = len(articles)
    upgraded = 0
    failed = 0

    for i, art in enumerate(articles, start=1):
        url = art["url"]
        try:
            html = fetch_url(url)
            full = extract_full_content(html, selectors)
        except Exception as exc:
            failed += 1
            logger.warning("Full content fetch failed: %s | %s", url, exc)
            print(f"      [{i}/{total}] FAILED  {url[:80]}")
            time.sleep(FULL_CONTENT_DELAY)
            continue

        if full and len(full) > len(art.get("content", "")):
            art["content"] = full
            upgraded += 1
            print(f"      [{i}/{total}] OK  {len(full)} chars  {url[:70]}")
        else:
            print(f"      [{i}/{total}] KEEP teaser ({len(art.get('content',''))} chars)")

        time.sleep(FULL_CONTENT_DELAY)

    print(f"    upgraded: {upgraded} | failed: {failed} | total: {total}")
    return articles


# ============================================================
# AUDIT
# ============================================================

def audit(config):
    path = DATA_DIR / config["output_file"]
    articles = load_existing(path)

    print()
    print("=" * 60)
    print(f"{config['source_name'].upper()} AUDIT")
    print("=" * 60)

    if not articles:
        print("No articles stored yet.")
        return

    lengths = sorted(len(a.get("content", "")) for a in articles)
    dates = sorted(a["published_date"] for a in articles if a.get("published_date"))
    urls = [normalize_url(a.get("url")) for a in articles]

    print("Articles     :", len(articles))
    print("Unique URLs  :", len(set(urls)))
    print("Missing date :", len(articles) - len(dates))
    if dates:
        print("Date range   :", dates[0], "->", dates[-1])
    if lengths:
        print("Content len  : min", lengths[0],
              "| median", lengths[len(lengths) // 2],
              "| max", lengths[-1])


# ============================================================
# RUN
# ============================================================

def run_scraper(config):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger = build_logger(config["source_name"], DATA_DIR / config["log_file"])

    output_path = DATA_DIR / config["output_file"]

    print()
    print("=" * 60)
    print(f"{config['source_name'].upper()} RSS SCRAPER")
    print("=" * 60)
    print(f"Feed : {config['feed_url']}")

    existing = load_existing(output_path)
    print(f"Existing articles: {len(existing)}")
    print()

    try:
        xml_text = fetch_url(config["feed_url"])
    except Exception as exc:
        print(f"Fetch failed: {exc}")
        logger.error("Fetch failed: %s", exc)
        return

    items = parse_rss_items(xml_text, config["source_name"])
    print(f"Parsed {len(items)} items from feed")

    if config.get("fetch_full_content") and items:
        print()
        print(f"Fetching full content ({config.get('content_selectors')})...")
        items = enrich_with_full_content(items, config, logger)

    merged = merge_articles(existing, items)
    save_json(output_path, merged)

    print()
    print("=" * 60)
    print("RUN COMPLETE")
    print("=" * 60)
    print("Fetched from feed:", len(items))
    print("Total stored     :", len(merged))
    print("Saved            :", output_path)


def main_for(config):
    parser = argparse.ArgumentParser(description=f"{config['source_name']} RSS scraper")
    parser.add_argument("--audit", action="store_true",
                        help="print a quality report and exit")
    args = parser.parse_args()

    if args.audit:
        audit(config)
    else:
        run_scraper(config)