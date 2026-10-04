"""
Analytics India Magazine scraper (sitemap -> Playwright -> clean article JSON)

Usage:
    python analytics_india_scraper.py                  # normal run (backfill or weekly, auto)
    python analytics_india_scraper.py --max-urls 0     # no per-run URL cap
    python analytics_india_scraper.py --audit          # content-quality report, no scraping
    python analytics_india_scraper.py --refetch-short  # re-extract suspiciously short articles
    python analytics_india_scraper.py --force-initial  # force backfill mode again
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
from playwright.sync_api import sync_playwright


# ============================================================
# CONFIG
# ============================================================

SOURCE_NAME = "Analytics India Magazine"

ROOT_SITEMAP_URL = "https://analyticsindiamag.com/ai-news-sitemap.xml"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

OUTPUT_FILE = DATA_DIR / "analytics_india.json"
STATE_FILE = DATA_DIR / "analytics_india_state.json"
FAILED_FILE = DATA_DIR / "analytics_india_failed_urls.json"
LOG_FILE = DATA_DIR / "analytics_india_scraper.log"

INITIAL_START_DATE = date(2026, 1, 1)

MAX_URLS_PER_RUN = 250
MAX_ATTEMPTS_PER_URL = 5
CHECKPOINT_EVERY = 25
RESTART_PAGE_AFTER_FAILURES = 5

MIN_CONTENT_CHARS = 300
SHORT_CONTENT_CHARS = 1200

PAGE_NAVIGATION_TIMEOUT = 30000
HYDRATION_WAIT_MS = 2500

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
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
# HTTP
# ============================================================

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
)


# ============================================================
# NOISE REMOVAL CONFIG
# ============================================================

NOISE_TAGS_SELECTOR = "script, style, noscript, nav, footer, aside, form, iframe, svg, button"

NOISE_TOKENS = [
    "share", "sharing", "social", "follow",
    "newsletter", "subscribe", "subscription",
    "advert", "advertisement", "ads", "ad", "adslot", "sponsored", "promo",
    "related", "recommended", "recommend", "trending",
    "comment", "comments", "sidebar", "breadcrumb", "breadcrumbs",
]

BAD_PHRASES = [
    "advertise with us",
    "subscribe to our newsletter",
    "follow us on",
    "related stories",
    "recommended stories",
    "what actually matters",
]


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
    text = text.replace("\xa0", " ")
    lines = []
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n\n".join(lines)


MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"],
        start=1,
    )
}


def parse_date_string(value):
    if not value:
        return None
    value = str(value).strip()

    match = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", value)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass

    match = re.search(
        r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+"
        r"(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d{2})\b",
        value,
        re.IGNORECASE,
    )
    if match:
        try:
            return date(
                int(match.group(3)),
                MONTHS[match.group(1).lower()],
                int(match.group(2)),
            )
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
    "initial_backfill_complete": False,
    "old_urls": {},
    "refetch": [],
    "last_run": None,
}


def load_state():
    state = deepcopy(DEFAULT_STATE)
    loaded = load_json(STATE_FILE, {})
    if isinstance(loaded, dict):
        state.update(loaded)
    if not isinstance(state.get("old_urls"), dict):
        state["old_urls"] = {}
    if not isinstance(state.get("refetch"), list):
        state["refetch"] = []
    return state


def save_state(state):
    state["last_run"] = datetime.now().isoformat(timespec="seconds")
    save_json(STATE_FILE, state)


# ============================================================
# FAILED URLS
# ============================================================

def load_failed_urls():
    data = load_json(FAILED_FILE, {})
    return data if isinstance(data, dict) else {}


def mark_failed(failed_urls, url, error):
    item = failed_urls.get(url, {"attempts": 0, "last_error": ""})
    item["attempts"] = item.get("attempts", 0) + 1
    item["last_error"] = str(error)
    item["last_attempt"] = datetime.now().isoformat(timespec="seconds")
    failed_urls[url] = item


# ============================================================
# EXISTING DATA
# ============================================================

def load_existing_articles():
    data = load_json(OUTPUT_FILE, [])
    return data if isinstance(data, list) else []


def merge_articles(existing, new_articles, prefer_longer=()):
    by_url = {}
    for article in existing:
        url = normalize_url(article.get("url"))
        if url:
            by_url[url] = article

    for article in new_articles:
        url = normalize_url(article.get("url"))
        if not url:
            continue
        old = by_url.get(url)
        if (
            old is not None
            and url in prefer_longer
            and len(old.get("content", "")) > len(article.get("content", ""))
        ):
            continue
        by_url[url] = article

    result = list(by_url.values())
    result.sort(key=lambda item: item.get("published_date") or "", reverse=True)
    return result


def checkpoint(existing, new_articles, failed_urls, state, prefer_longer=()):
    merged = merge_articles(existing, new_articles, prefer_longer)
    save_json(OUTPUT_FILE, merged)
    save_json(FAILED_FILE, failed_urls)
    save_state(state)
    return merged


# ============================================================
# SITEMAP
# ============================================================

def fetch_sitemap(url, retries=3):
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            response = SESSION.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as exc:
            last_exc = exc
            logger.warning("Sitemap fetch %s failed (%s/%s): %s", url, attempt, retries, exc)
            time.sleep(2 * attempt)
    raise last_exc


def parse_sitemap(xml_text):
    soup = BeautifulSoup(xml_text, "xml")

    children = []
    for sm in soup.find_all("sitemap"):
        loc = sm.find("loc")
        if loc and loc.get_text(strip=True):
            children.append(loc.get_text(strip=True))

    entries = []
    for node in soup.find_all("url"):
        loc = node.find("loc")
        if not loc or not loc.get_text(strip=True):
            continue

        lastmod = node.find("lastmod")
        pub = node.find(re.compile(r"(^|:)publication_date$"))

        entries.append(
            {
                "url": loc.get_text(strip=True),
                "lastmod": parse_date_string(lastmod.get_text(strip=True)) if lastmod else None,
                "pub": parse_date_string(pub.get_text(strip=True)) if pub else None,
            }
        )

    return children, entries


def get_article_entries():
    logger.info("Fetching AIM AI-News sitemap: %s", ROOT_SITEMAP_URL)

    all_entries = []
    to_visit = [(ROOT_SITEMAP_URL, 0)]
    visited = set()

    while to_visit:
        url, depth = to_visit.pop(0)
        if url in visited or depth > 2:
            continue
        visited.add(url)

        children, entries = parse_sitemap(fetch_sitemap(url))
        all_entries.extend(entries)

        for child in children:
            to_visit.append((child, depth + 1))

    unique = {}
    for entry in all_entries:
        url = normalize_url(entry["url"])
        if not url or "/ai-news/" not in url:
            continue
        entry["url"] = url
        if url not in unique:
            unique[url] = entry
        else:
            for key in ("pub", "lastmod"):
                unique[url][key] = unique[url][key] or entry[key]

    entries = list(unique.values())
    entries.sort(
        key=lambda e: (
            (e["pub"] or e["lastmod"]) is None,
            -((e["pub"] or e["lastmod"]).toordinal() if (e["pub"] or e["lastmod"]) else 0),
        )
    )
    return entries


# ============================================================
# DATE EXTRACTION
# ============================================================

def extract_date_from_jsonld(page):
    scripts = page.locator("script[type='application/ld+json']")
    for i in range(scripts.count()):
        try:
            data = json.loads(scripts.nth(i).inner_text())
            objects = []
            if isinstance(data, dict):
                objects.append(data)
                graph = data.get("@graph")
                if isinstance(graph, list):
                    objects.extend(graph)
            elif isinstance(data, list):
                objects.extend(data)

            for obj in objects:
                if not isinstance(obj, dict):
                    continue
                value = obj.get("datePublished") or obj.get("dateCreated")
                parsed = parse_date_string(value) if value else None
                if parsed:
                    return parsed
        except Exception:
            continue
    return None


def extract_publication_date(page):
    parsed = extract_date_from_jsonld(page)
    if parsed:
        return parsed

    for selector in [
        "meta[property='article:published_time']",
        "meta[name='article:published_time']",
        "meta[name='publish_date']",
        "meta[name='date']",
        "meta[itemprop='datePublished']",
    ]:
        locator = page.locator(selector)
        if locator.count() == 0:
            continue
        try:
            parsed = parse_date_string(locator.first.get_attribute("content") or "")
            if parsed:
                return parsed
        except Exception:
            pass

    times = page.locator("article time, main time")
    for i in range(min(times.count(), 10)):
        try:
            node = times.nth(i)
            parsed = parse_date_string(node.get_attribute("datetime") or "")
            if not parsed:
                parsed = parse_date_string(node.inner_text() or "")
            if parsed:
                return parsed
        except Exception:
            continue

    try:
        nearby = page.evaluate(
            """
            () => {
                const h = document.querySelector("h1");
                if (!h) return "";
                let n = h;
                for (let i = 0; i < 3 && n.parentElement; i++) n = n.parentElement;
                return (n.innerText || "").slice(0, 1500);
            }
            """
        )
        return parse_date_string(nearby)
    except Exception:
        return None


# ============================================================
# ARTICLE EXTRACTION
# ============================================================

EXTRACT_JS = """
(root, args) => {
    const noiseTokens = new Set(args.noiseTokens);
    const badPhrases = args.badPhrases;

    const isNoise = (el) => {
        const cls = typeof el.className === "string" ? el.className : "";
        const raw = (cls + " " + (el.id || "")).toLowerCase();
        return raw.split(/[^a-z0-9]+/).some(t => noiseTokens.has(t));
    };

    const clone = root.cloneNode(true);

    clone.querySelectorAll(args.noiseTags).forEach(el => el.remove());

    clone.querySelectorAll("*").forEach(el => {
        if (isNoise(el) && (el.textContent || "").length < 500) el.remove();
    });

    const parts = [];
    const seen = new Set();
    let bodyLen = 0;

    const candidates = clone.querySelectorAll("p, h2, h3, li, div");
    candidates.forEach(el => {
        const tag = el.tagName.toLowerCase();

        if (tag === "div") {
            const hasBlock = el.querySelector(
                "p, div, h1, h2, h3, h4, h5, h6, ul, ol, table, article, section, aside, blockquote"
            );
            if (hasBlock) return;
        }

        if (tag === "li" && el.querySelector("p")) return;

        const text = (el.textContent || "").replace(/\\s+/g, " ").trim();
        if (!text) return;

        if (tag === "h2" || tag === "h3") {
            if (text.length >= 4 && text.length <= 200) {
                parts.push({ heading: true, text: text });
            }
            return;
        }

        if (text.length < 30) return;

        const linkLen = Array.from(el.querySelectorAll("a"))
            .reduce((sum, a) => sum + (a.textContent || "").trim().length, 0);

        if (text.length < 200 && linkLen / text.length > 0.7) return;
        if (/^(also read|read more|read:|also see|related:|advertisement)/i.test(text)) return;

        const lower = text.toLowerCase();
        if (text.length < 250 && badPhrases.some(p => lower.includes(p))) return;

        if (seen.has(text)) return;
        seen.add(text);

        parts.push({ heading: false, text: text });
        bodyLen += text.length;
    });

    while (parts.length && parts[0].heading) parts.shift();
    while (parts.length && parts[parts.length - 1].heading) parts.pop();

    const joined = parts.map(p => p.text).join("\\n\\n");

    return {
        content: joined,
        bodyLen: bodyLen,
        paragraphCount: parts.filter(p => !p.heading).length,
    };
}
"""


GENERIC_OG_TITLE = "AIM — India's Leading AI & Data Science Media Platform"


def pick_title(page):
    """
    Prefer og:title — but skip the generic site-wide og:title that AIM
    sometimes serves on article pages.

    Fall back to the first non-empty H1.
    """
    loc = page.locator("meta[property='og:title']")
    if loc.count() > 0:
        try:
            title = (loc.first.get_attribute("content") or "").strip()
            if title and title != GENERIC_OG_TITLE:
                for suffix in (
                    " | Analytics India Magazine",
                    " - Analytics India Magazine",
                    " | AIM",
                ):
                    if title.endswith(suffix):
                        title = title[: -len(suffix)].strip()
                return title
        except Exception:
            pass

    for selector in ("article h1", "main h1", "h1"):
        h1s = page.locator(selector)
        for i in range(min(h1s.count(), 10)):
            node = h1s.nth(i)
            try:
                title = " ".join(node.inner_text().split())
            except Exception:
                continue
            if title:
                return title

    return ""


def _collect_candidates(page):
    """
    Return a list of Playwright locators likely to hold the article body,
    ordered by confidence:
      1. <article> that contains the first non-empty H1
      2. All <article> tags with meaningful text
      3. <main>
    """
    candidates = []

    # 1. Article that contains the first non-empty H1
    h1s = page.locator("h1")
    for i in range(min(h1s.count(), 5)):
        node = h1s.nth(i)
        try:
            t = node.inner_text().strip()
        except Exception:
            continue
        if not t:
            continue
        art = node.locator("xpath=ancestor::article[1]")
        if art.count() > 0:
            candidates.append(art.first)
        break

    # 2. All <article> tags
    arts = page.locator("article")
    for i in range(min(arts.count(), 5)):
        try:
            art_len = len(arts.nth(i).inner_text())
        except Exception:
            continue
        if art_len > 300:
            candidates.append(arts.nth(i))

    # 3. <main>
    mains = page.locator("main")
    if mains.count() > 0:
        candidates.append(mains.first)

    return candidates


def extract_article(page, url, publication_date):
    try:
        title = pick_title(page)
        if not title:
            return None

        if title.lower() in {
            "advertise with us",
            "subscribe to our newsletter",
            "what actually matters.",
        }:
            return None

        candidates = _collect_candidates(page)
        if not candidates:
            logger.warning("No article container found: %s", url)
            return None

        best_content = ""
        best_result = None

        for cand in candidates:
            try:
                r = cand.evaluate(
                    EXTRACT_JS,
                    {
                        "noiseTags": NOISE_TAGS_SELECTOR,
                        "noiseTokens": NOISE_TOKENS,
                        "badPhrases": BAD_PHRASES,
                    },
                )
            except Exception:
                continue
            if not r:
                continue
            c = clean_text(r.get("content", ""))
            if len(c) > len(best_content):
                best_content = c
                best_result = r

        if not best_content:
            return None

        if len(best_content) < MIN_CONTENT_CHARS:
            logger.warning("Content too short (rejected): %s | %s chars", url, len(best_content))
            return None

        if len(best_content) < SHORT_CONTENT_CHARS:
            logger.warning(
                "Short article kept: %s | %s chars | %s paragraphs",
                url, len(best_content), best_result.get("paragraphCount"),
            )

        return {
            "title": title,
            "source": SOURCE_NAME,
            "url": normalize_url(url),
            "published_date": publication_date.isoformat(),
            "content": best_content,
        }

    except Exception as exc:
        logger.exception("Article extraction failed: %s | %s", url, exc)
        return None


# ============================================================
# PLAYWRIGHT
# ============================================================

def create_browser_context(browser):
    return browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1440, "height": 900},
    )


def prepare_page(context):
    page = context.new_page()

    def handle_route(route):
        if route.request.resource_type in {"image", "media", "font"}:
            route.abort()
            return
        route.continue_()

    page.route("**/*", handle_route)
    return page


def load_article_page(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=PAGE_NAVIGATION_TIMEOUT)
    page.wait_for_timeout(HYDRATION_WAIT_MS)

    # AIM lazy-loads the article body. Wait for any loading skeleton
    # (Tailwind's animate-pulse class) to disappear before extraction.
    try:
        page.wait_for_selector(".animate-pulse", state="detached", timeout=6000)
    except Exception:
        pass

    try:
        page.locator("h1").first.wait_for(state="visible", timeout=10000)
    except Exception:
        pass


# ============================================================
# DATE RANGE
# ============================================================

def current_week_start():
    today = date.today()
    return today - timedelta(days=today.weekday())


# ============================================================
# QUEUE
# ============================================================

def build_queue(entries, stored, state, failed_urls, initial_mode):
    week_start = current_week_start()
    refetch = set(state["refetch"])
    old_urls = state["old_urls"]

    def capped(url):
        return failed_urls.get(url, {}).get("attempts", 0) >= MAX_ATTEMPTS_PER_URL

    queue = []
    seen = set()

    for entry in entries:
        url = entry["url"]
        if url in seen:
            continue
        seen.add(url)

        hint = entry["pub"] or entry["lastmod"]

        if url in refetch:
            queue.append((url, INITIAL_START_DATE, entry["pub"]))
            continue

        if url in old_urls or capped(url):
            continue

        if url in failed_urls and url not in stored:
            queue.append((url, INITIAL_START_DATE, entry["pub"]))
            continue

        if initial_mode:
            if url in stored:
                continue
            if hint and hint < INITIAL_START_DATE:
                old_urls[url] = hint.isoformat()
                continue
            queue.append((url, INITIAL_START_DATE, entry["pub"]))
        else:
            if hint and hint < week_start:
                continue
            stored_date = stored.get(url)
            if url in stored and stored_date and stored_date < week_start:
                continue
            queue.append((url, week_start, entry["pub"]))

    for url in list(failed_urls):
        if url in seen or capped(url) or url in stored or url in old_urls:
            continue
        seen.add(url)
        queue.append((url, INITIAL_START_DATE, None))

    for url in sorted(refetch):
        if url not in seen:
            seen.add(url)
            queue.append((url, INITIAL_START_DATE, None))

    return queue


# ============================================================
# ARTICLE PROCESSING
# ============================================================

def process_article(page, url, min_date, pub_hint):
    try:
        load_article_page(page, url)

        publication_date = pub_hint or extract_publication_date(page)

        if not publication_date:
            return "failed", "no publication date found"

        if publication_date < min_date:
            return "old", publication_date.isoformat()

        if publication_date > date.today() + timedelta(days=1):
            return "failed", f"publication date in the future: {publication_date}"

        article = extract_article(page, url, publication_date)
        if not article:
            return "failed", "content extraction failed or too short"

        return "success", article

    except Exception as exc:
        logger.error("Failed URL: %s | %s", url, exc)
        return "failed", f"{type(exc).__name__}: {exc}"


# ============================================================
# AUDIT / REFETCH
# ============================================================

def audit():
    articles = load_existing_articles()

    print()
    print("=" * 60)
    print("CONTENT AUDIT")
    print("=" * 60)

    if not articles:
        print("No articles stored yet.")
        return

    lengths = sorted(len(a.get("content", "")) for a in articles)
    dates = sorted(a["published_date"] for a in articles if a.get("published_date"))
    urls = [normalize_url(a.get("url")) for a in articles]

    print("Articles           :", len(articles))
    print("Unique URLs        :", len(set(urls)))
    print("Missing date       :", len(articles) - len(dates))
    if dates:
        print("Date range         :", dates[0], "->", dates[-1])

    print("Content length     : min", lengths[0],
          "| median", lengths[len(lengths) // 2], "| max", lengths[-1])

    buckets = [(0, 600), (600, 1200), (1200, 2500), (2500, 5000), (5000, 10**9)]
    for low, high in buckets:
        count = sum(1 for n in lengths if low <= n < high)
        label = f"{low}-{high}" if high < 10**9 else f"{low}+"
        print(f"  {label:>10} chars : {count}")

    print()
    print("15 shortest articles:")
    for article in sorted(articles, key=lambda a: len(a.get("content", "")))[:15]:
        print(f"  {len(article.get('content', '')):>5} | {article.get('published_date')} | {article.get('url')}")

    short = sum(1 for n in lengths if n < SHORT_CONTENT_CHARS)
    print()
    print(f"{short} articles are under {SHORT_CONTENT_CHARS} chars. "
          f"Open a few of the URLs above: if the real article is longer, "
          f"run with --refetch-short.")


def mark_short_for_refetch(state):
    articles = load_existing_articles()
    urls = [
        normalize_url(a.get("url"))
        for a in articles
        if a.get("url") and len(a.get("content", "")) < SHORT_CONTENT_CHARS
    ]
    state["refetch"] = sorted(set(state["refetch"]) | set(urls))
    state["initial_backfill_complete"] = False
    save_state(state)
    print(f"Marked {len(urls)} short articles for re-extraction.")


# ============================================================
# RUN
# ============================================================

def run(args):
    print()
    print("=" * 60)
    print("ANALYTICS INDIA MAGAZINE SCRAPER")
    print("=" * 60)

    state = load_state()

    if args.refetch_short:
        mark_short_for_refetch(state)

    initial_mode = args.force_initial or not state["initial_backfill_complete"]

    if initial_mode:
        print("MODE: INITIAL BACKFILL")
        print(f"DATE RANGE: {INITIAL_START_DATE} -> {date.today()}")
    else:
        print("MODE: WEEKLY REFRESH")
        print(f"DATE RANGE: {current_week_start()} -> {date.today()}")

    print()
    print("Fetching sitemap...")

    entries = get_article_entries()
    print(f"Unique AI-News URLs in sitemap: {len(entries)}")

    if not entries:
        print("No URLs found.")
        return

    existing = load_existing_articles()
    failed_urls = load_failed_urls()

    stored = {
        normalize_url(a.get("url")): parse_date_string(a.get("published_date"))
        for a in existing
        if a.get("url")
    }

    full_queue = build_queue(entries, stored, state, failed_urls, initial_mode)

    max_urls = args.max_urls
    queue = full_queue if max_urls == 0 else full_queue[:max_urls]

    print(f"Pending in this mode: {len(full_queue)} | processing now: {len(queue)}")

    refetch = set(state["refetch"])
    refetch_original = set(refetch)

    new_articles = []
    successful = failed = old_count = 0
    consecutive_failures = 0
    finished = False

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = create_browser_context(browser)
        page = prepare_page(context)

        try:
            for number, (url, min_date, pub_hint) in enumerate(queue, start=1):
                print(f"[{number}/{len(queue)}] {url}")

                status, payload = process_article(page, url, min_date, pub_hint)

                if status == "success":
                    successful += 1
                    consecutive_failures = 0
                    new_articles.append(payload)
                    failed_urls.pop(url, None)
                    refetch.discard(url)
                    print("  OK:", payload["published_date"], "|", len(payload["content"]), "chars")

                elif status == "old":
                    old_count += 1
                    consecutive_failures = 0
                    failed_urls.pop(url, None)
                    refetch.discard(url)
                    if min_date == INITIAL_START_DATE:
                        state["old_urls"][url] = payload
                    print("  OLD / OUT OF RANGE:", payload)

                else:
                    failed += 1
                    consecutive_failures += 1
                    refetch.discard(url)
                    mark_failed(failed_urls, url, payload)
                    print("  FAILED:", payload)

                if number % CHECKPOINT_EVERY == 0:
                    state["refetch"] = sorted(refetch)
                    existing = checkpoint(
                        existing, new_articles, failed_urls, state, refetch_original
                    )
                    new_articles = []

                if consecutive_failures >= RESTART_PAGE_AFTER_FAILURES:
                    print("  Too many failures in a row, restarting browser context...")
                    logger.warning("Restarting browser context after %s failures", consecutive_failures)
                    try:
                        context.close()
                    except Exception:
                        pass
                    context = create_browser_context(browser)
                    page = prepare_page(context)
                    consecutive_failures = 0

                time.sleep(0.15)

            finished = True

        finally:
            try:
                context.close()
                browser.close()
            except Exception:
                pass

            state["refetch"] = sorted(refetch)
            merged = checkpoint(
                existing, new_articles, failed_urls, state, refetch_original
            )

    if initial_mode and finished and len(full_queue) <= len(queue):
        state["initial_backfill_complete"] = True
        save_state(state)

    capped = sum(
        1 for v in failed_urls.values()
        if v.get("attempts", 0) >= MAX_ATTEMPTS_PER_URL
    )

    print()
    print("=" * 60)
    print("RUN COMPLETE")
    print("=" * 60)
    print("Successful          :", successful)
    print("Failed (this run)   :", failed)
    print("Old/out of range    :", old_count)
    print("Still pending       :", max(len(full_queue) - len(queue), 0))
    print("Failed URLs on file :", len(failed_urls), f"({capped} gave up after {MAX_ATTEMPTS_PER_URL} tries)")
    print("Total stored        :", len(merged))
    print("Backfill complete   :", state["initial_backfill_complete"])
    print()
    print("Saved:", OUTPUT_FILE)

    if not state["initial_backfill_complete"]:
        print("Run again to continue the backfill (or use --max-urls 0 to do it in one go).")


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Analytics India Magazine scraper")
    parser.add_argument("--max-urls", type=int, default=MAX_URLS_PER_RUN,
                        help="max URLs to visit this run (0 = unlimited)")
    parser.add_argument("--audit", action="store_true",
                        help="print a content-quality report and exit")
    parser.add_argument("--refetch-short", action="store_true",
                        help=f"re-extract stored articles shorter than {SHORT_CONTENT_CHARS} chars")
    parser.add_argument("--force-initial", action="store_true",
                        help="run in initial-backfill mode even if marked complete")
    args = parser.parse_args()

    if args.audit:
        audit()
        return

    run(args)


if __name__ == "__main__":
    main()