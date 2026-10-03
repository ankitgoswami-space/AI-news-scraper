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

ROOT_SITEMAP_URL = (
    "https://analyticsindiamag.com/ai-news-sitemap.xml"
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

OUTPUT_FILE = DATA_DIR / "analytics_india.json"
STATE_FILE = DATA_DIR / "analytics_india_state.json"
FAILED_FILE = DATA_DIR / "analytics_india_failed_urls.json"
LOG_FILE = DATA_DIR / "analytics_india_scraper.log"

INITIAL_START_DATE = date(2026, 1, 1)

# Maximum sitemap URLs inspected in one run.
MAX_URLS_PER_RUN = 250

# Used when looking for the date boundary.
CONSECUTIVE_OLD_REQUIRED = 30

MAX_FAILED_RETRIES = 50

PAGE_NAVIGATION_TIMEOUT = 30000
HYDRATION_WAIT_MS = 1200

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/154.0.0.0 Safari/537.36"
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
# SELECTORS TO REMOVE
# ============================================================

REMOVE_SELECTORS = [
    "script",
    "style",
    "noscript",
    "nav",
    "footer",
    "aside",
    "form",
    "iframe",
    "svg",

    # sharing / social
    "[class*='share']",
    "[class*='social']",
    "[class*='follow']",

    # newsletter
    "[class*='newsletter']",
    "[id*='newsletter']",
    "[class*='subscribe']",

    # advertising
    "[class*='advert']",
    "[class*='advertisement']",
    "[class*='ads']",
    "[id*='advert']",
    "[id*='ads']",

    # related/recommended
    "[class*='related']",
    "[class*='recommended']",
    "[class*='recommend']",

    # comments
    "[class*='comment']",
    "[id*='comment']",
]


# ============================================================
# BASIC HELPERS
# ============================================================

def normalize_url(url):
    if not url:
        return ""

    url = url.strip()

    parsed = urlparse(url)

    clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    clean = clean.rstrip("/")

    return clean


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


def parse_date_string(value):
    if not value:
        return None

    value = value.strip()

    # ISO date
    match = re.search(
        r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})",
        value,
    )

    if match:
        try:
            return date(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
            )
        except ValueError:
            pass

    # Example:
    # October 1, 2026
    # OCTOBER 1, 2026, 6:48 PM
    patterns = [
        "%B %d, %Y",
        "%B %d, %Y, %I:%M %p",
        "%b %d, %Y",
        "%b %d, %Y, %I:%M %p",
    ]

    for pattern in patterns:
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue

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
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )

    temp_path.replace(path)


# ============================================================
# STATE
# ============================================================

def load_state():
    return load_json(
        STATE_FILE,
        {
            "initial_backfill_complete": False,
            "last_cursor_url": None,
            "last_run": None,
        },
    )


def save_state(state):
    state["last_run"] = datetime.now().isoformat(
        timespec="seconds"
    )

    save_json(STATE_FILE, state)


# ============================================================
# FAILED URLS
# ============================================================

def load_failed_urls():
    data = load_json(
        FAILED_FILE,
        {},
    )

    if not isinstance(data, dict):
        return {}

    return data


def save_failed_urls(data):
    save_json(FAILED_FILE, data)


def mark_failed(failed_urls, url, error):
    item = failed_urls.get(
        url,
        {
            "attempts": 0,
            "last_error": "",
        },
    )

    item["attempts"] += 1
    item["last_error"] = str(error)
    item["last_attempt"] = datetime.now().isoformat(
        timespec="seconds"
    )

    failed_urls[url] = item


# ============================================================
# EXISTING DATA
# ============================================================

def load_existing_articles():
    data = load_json(
        OUTPUT_FILE,
        [],
    )

    if not isinstance(data, list):
        return []

    return data


def merge_articles(existing, new_articles):
    by_url = {}

    for article in existing:
        url = normalize_url(article.get("url"))

        if url:
            by_url[url] = article

    for article in new_articles:
        url = normalize_url(article.get("url"))

        if url:
            by_url[url] = article

    result = list(by_url.values())

    result.sort(
        key=lambda item: item.get(
            "published_date",
            "",
        ),
        reverse=True,
    )

    return result


# ============================================================
# SITEMAP
# ============================================================

def fetch_sitemap(url):
    response = SESSION.get(
        url,
        timeout=30,
    )

    response.raise_for_status()

    return response.text


def parse_sitemap(xml_text):
    soup = BeautifulSoup(
        xml_text,
        "xml",
    )

    urls = []

    for loc in soup.find_all("loc"):
        value = loc.get_text(
            strip=True
        )

        if value:
            urls.append(value)

    return urls


def get_article_urls():
    logger.info(
        "Fetching AIM AI-News sitemap: %s",
        ROOT_SITEMAP_URL,
    )

    xml = fetch_sitemap(
        ROOT_SITEMAP_URL
    )

    urls = parse_sitemap(xml)

    normalized = []

    seen = set()

    for url in urls:
        url = normalize_url(url)

        if not url:
            continue

        if "/ai-news/" not in url:
            continue

        if url in seen:
            continue

        seen.add(url)
        normalized.append(url)

    return normalized


# ============================================================
# DATE EXTRACTION
# ============================================================

def extract_date_from_jsonld(page):
    scripts = page.locator(
        "script[type='application/ld+json']"
    )

    for i in range(scripts.count()):
        try:
            raw = scripts.nth(i).inner_text()

            data = json.loads(raw)

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

                value = (
                    obj.get("datePublished")
                    or obj.get("dateCreated")
                )

                parsed = parse_date_string(
                    str(value)
                )

                if parsed:
                    return parsed

        except Exception:
            continue

    return None


def extract_publication_date(page):
    # --------------------------------------------------------
    # 1. JSON-LD
    # --------------------------------------------------------

    parsed = extract_date_from_jsonld(page)

    if parsed:
        return parsed

    # --------------------------------------------------------
    # 2. Meta tags
    # --------------------------------------------------------

    meta_selectors = [
        "meta[property='article:published_time']",
        "meta[name='article:published_time']",
        "meta[name='publish_date']",
        "meta[name='date']",
        "meta[itemprop='datePublished']",
    ]

    for selector in meta_selectors:
        locator = page.locator(selector)

        if locator.count() == 0:
            continue

        try:
            value = locator.first.get_attribute(
                "content"
            )

            parsed = parse_date_string(
                value or ""
            )

            if parsed:
                return parsed

        except Exception:
            pass

    # --------------------------------------------------------
    # 3. Global <time>
    # --------------------------------------------------------

    times = page.locator("time")

    for i in range(times.count()):
        try:
            node = times.nth(i)

            datetime_value = node.get_attribute(
                "datetime"
            )

            text_value = node.inner_text()

            parsed = parse_date_string(
                datetime_value or ""
            )

            if not parsed:
                parsed = parse_date_string(
                    text_value or ""
                )

            if parsed:
                return parsed

        except Exception:
            continue

    # --------------------------------------------------------
    # 4. Visible body text fallback
    # --------------------------------------------------------

    try:
        body = page.locator("body").inner_text()

        patterns = [
            r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d{2}",
            r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+20\d{2}",
        ]

        for pattern in patterns:
            match = re.search(
                pattern,
                body,
                re.IGNORECASE,
            )

            if match:
                parsed = parse_date_string(
                    match.group(0)
                )

                if parsed:
                    return parsed

    except Exception:
        pass

    return None


# ============================================================
# ARTICLE EXTRACTION
# ============================================================

def extract_article(
    page,
    url,
    publication_date,
):
    """
    Extract article content using the page H1 as the anchor.

    We walk upward from the H1 and score candidate containers.
    """

    try:
        h1 = page.locator("h1").first

        if h1.count() == 0:
            return None

        page_title = clean_text(
            h1.inner_text()
        )

        if not page_title:
            return None

        result = page.evaluate(
            """
            (args) => {

                const pageTitle = args.pageTitle;
                const removeSelectors = args.removeSelectors;

                const h1 = Array.from(
                    document.querySelectorAll("h1")
                ).find(
                    el => (el.innerText || "").trim() === pageTitle
                );

                if (!h1) {
                    return null;
                }

                let best = null;
                let bestScore = -Infinity;

                let node = h1;

                for (
                    let level = 0;
                    level < 8 && node;
                    level++
                ) {

                    const clone = node.cloneNode(true);

                    for (const selector of removeSelectors) {
                        try {
                            clone.querySelectorAll(selector)
                                .forEach(el => el.remove());
                        } catch (e) {
                            // Ignore invalid/missing selector.
                        }
                    }

                    const paragraphs = Array.from(
                        clone.querySelectorAll("p")
                    )
                    .map(
                        p => (p.innerText || "").trim()
                    )
                    .filter(
                        text => text.length > 40
                    );

                    const paragraphText =
                        paragraphs.join("\\n\\n");

                    const fullText =
                        (clone.innerText || "").trim();

                    if (!fullText) {
                        node = node.parentElement;
                        continue;
                    }

                    const lower =
                        fullText.toLowerCase();

                    const badPhrases = [
                        "advertise with us",
                        "what actually matters.",
                        "subscribe to our newsletter",
                        "follow us",
                        "read more",
                        "related stories",
                        "recommended stories"
                    ];

                    let badPhraseCount = 0;

                    for (
                        const phrase of badPhrases
                    ) {
                        if (lower.includes(phrase)) {
                            badPhraseCount++;
                        }
                    }

                    let score = 0;

                    // Candidate contains exact article title.
                    if (fullText.includes(pageTitle)) {
                        score += 200;
                    }

                    // Prefer real paragraph content.
                    score += Math.min(
                        paragraphs.length * 25,
                        250
                    );

                    // Prefer substantial article body.
                    if (paragraphText.length >= 5000) {
                        score += 300;
                    } else if (
                        paragraphText.length >= 3000
                    ) {
                        score += 250;
                    } else if (
                        paragraphText.length >= 1500
                    ) {
                        score += 180;
                    } else if (
                        paragraphText.length >= 800
                    ) {
                        score += 100;
                    } else if (
                        paragraphText.length >= 400
                    ) {
                        score += 50;
                    }

                    score -=
                        badPhraseCount * 120;

                    if (paragraphText.length < 300) {
                        score -= 250;
                    }

                    if (score > bestScore) {

                        bestScore = score;

                        best = {
                            title: pageTitle,
                            content: paragraphText,
                            paragraphCount:
                                paragraphs.length,
                            score: score
                        };
                    }

                    node = node.parentElement;
                }

                return best;
            }
            """,
            {
                "pageTitle": page_title,
                "removeSelectors": REMOVE_SELECTORS,
            },
        )

        if not result:
            return None

        content = clean_text(
            result.get("content", "")
        )

        title = clean_text(
            result.get("title", "")
        )

        # ----------------------------------------------------
        # Validation
        # ----------------------------------------------------

        if not title:
            return None

        if len(content) < 300:
            logger.warning(
                "Content too short: %s | %s chars",
                url,
                len(content),
            )
            return None

        # Avoid known non-article containers.
        bad_titles = {
            "advertise with us",
            "subscribe to our newsletter",
            "what actually matters.",
        }

        if title.lower() in bad_titles:
            return None

        return {
            "title": title,
            "source": SOURCE_NAME,
            "url": normalize_url(url),
            "published_date": (
                publication_date.isoformat()
                if publication_date
                else None
            ),
            "content": content,
        }

    except Exception as exc:
        logger.exception(
            "Article extraction failed: %s | %s",
            url,
            exc,
        )

        return None


# ============================================================
# PLAYWRIGHT
# ============================================================

def create_browser_context(browser):
    return browser.new_context(
        user_agent=USER_AGENT,
        viewport={
            "width": 1440,
            "height": 900,
        },
    )


def prepare_page(context):
    page = context.new_page()

    # Block heavy resources only.
    def handle_route(route):
        resource_type = route.request.resource_type

        if resource_type in {
            "image",
            "media",
            "font",
        }:
            route.abort()
            return

        route.continue_()

    page.route(
        "**/*",
        handle_route,
    )

    return page


def load_article_page(page, url):
    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=PAGE_NAVIGATION_TIMEOUT,
    )

    page.wait_for_timeout(
        HYDRATION_WAIT_MS
    )

    # Wait for H1 if available.
    try:
        page.locator("h1").first.wait_for(
            state="visible",
            timeout=10000,
        )
    except Exception:
        pass


# ============================================================
# DATE RANGE
# ============================================================

def current_week_start():
    today = date.today()

    # Monday = 0
    return today - timedelta(
        days=today.weekday()
    )


def is_valid_initial_date(pub_date):
    return (
        pub_date is not None
        and INITIAL_START_DATE
        <= pub_date
        <= date.today()
    )


def is_valid_weekly_date(pub_date):
    if not pub_date:
        return False

    return (
        current_week_start()
        <= pub_date
        <= date.today()
    )


# ============================================================
# MAIN PROCESSING
# ============================================================

def process_article(
    page,
    url,
    initial_mode,
):
    try:
        load_article_page(
            page,
            url,
        )

        publication_date = (
            extract_publication_date(page)
        )

        if not publication_date:
            return (
                "no_date",
                None,
            )

        if initial_mode:

            if not is_valid_initial_date(
                publication_date
            ):
                return (
                    "old",
                    None,
                )

        else:

            if not is_valid_weekly_date(
                publication_date
            ):
                return (
                    "old",
                    None,
                )

        article = extract_article(
            page,
            url,
            publication_date,
        )

        if not article:
            return (
                "failed",
                None,
            )

        return (
            "success",
            article,
        )

    except Exception as exc:

        logger.error(
            "Failed URL: %s | %s",
            url,
            exc,
        )

        return (
            "failed",
            None,
        )


# ============================================================
# RUN
# ============================================================

def run():
    print()
    print("=" * 60)
    print("ANALYTICS INDIA MAGAZINE SCRAPER")
    print("=" * 60)

    state = load_state()

    initial_mode = not state.get(
        "initial_backfill_complete",
        False,
    )

    if initial_mode:
        print(
            "MODE: INITIAL BACKFILL"
        )
        print(
            f"DATE RANGE: {INITIAL_START_DATE} -> {date.today()}"
        )
    else:
        print(
            "MODE: WEEKLY REFRESH"
        )
        print(
            f"DATE RANGE: {current_week_start()} -> {date.today()}"
        )

    # --------------------------------------------------------
    # Sitemap
    # --------------------------------------------------------

    print()
    print("Fetching sitemap...")

    urls = get_article_urls()

    print(
        f"Unique AI-News URLs: {len(urls)}"
    )

    if not urls:
        print(
            "No URLs found."
        )
        return

    # --------------------------------------------------------
    # Cursor
    # --------------------------------------------------------

    cursor_url = state.get(
        "last_cursor_url"
    )

    start_index = 0

    if cursor_url:

        normalized_cursor = normalize_url(
            cursor_url
        )

        for index, url in enumerate(urls):

            if normalize_url(url) == normalized_cursor:
                start_index = index + 1
                break

    # --------------------------------------------------------
    # For weekly mode always start from newest.
    # --------------------------------------------------------

    if not initial_mode:
        start_index = 0

    urls_to_process = urls[
        start_index:
        start_index + MAX_URLS_PER_RUN
    ]

    print(
        f"Processing: {len(urls_to_process)} URLs"
    )

    # --------------------------------------------------------
    # Existing data
    # --------------------------------------------------------

    existing = load_existing_articles()

    failed_urls = load_failed_urls()

    new_articles = []

    successful = 0
    failed = 0
    old_count = 0
    no_date = 0

    # --------------------------------------------------------
    # Browser
    # --------------------------------------------------------

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True
        )

        context = create_browser_context(
            browser
        )

        page = prepare_page(
            context
        )

        try:

            consecutive_old = 0

            for number, url in enumerate(
                urls_to_process,
                start=1,
            ):

                print(
                    f"[{number}/{len(urls_to_process)}] {url}"
                )

                status, article = process_article(
                    page,
                    url,
                    initial_mode,
                )

                if status == "success":

                    successful += 1

                    consecutive_old = 0

                    new_articles.append(
                        article
                    )

                    print(
                        "  OK:",
                        article["published_date"],
                        "|",
                        len(article["content"]),
                        "chars",
                    )

                    failed_urls.pop(
                        normalize_url(url),
                        None,
                    )

                elif status == "old":

                    old_count += 1

                    consecutive_old += 1

                    print(
                        "  OLD / OUT OF RANGE"
                    )

                elif status == "no_date":

                    no_date += 1

                    consecutive_old = 0

                    print(
                        "  NO PUBLICATION DATE"
                    )

                else:

                    failed += 1

                    consecutive_old = 0

                    mark_failed(
                        failed_urls,
                        normalize_url(url),
                        "article extraction failed",
                    )

                    print(
                        "  FAILED"
                    )

                # Stop when we've crossed the relevant
                # date boundary in the newest-first sitemap.
                if (
                    consecutive_old
                    >= CONSECUTIVE_OLD_REQUIRED
                ):

                    print(
                        "Date boundary reached."
                    )

                    break

                time.sleep(0.15)

        finally:

            context.close()
            browser.close()

    # --------------------------------------------------------
    # Merge
    # --------------------------------------------------------

    merged = merge_articles(
        existing,
        new_articles,
    )

    save_json(
        OUTPUT_FILE,
        merged,
    )

    save_failed_urls(
        failed_urls
    )

    # --------------------------------------------------------
    # Cursor
    # --------------------------------------------------------

    if urls_to_process:

        last_processed_url = urls_to_process[-1]

        state["last_cursor_url"] = (
            last_processed_url
        )

    # Initial backfill becomes complete only when
    # we actually crossed the Jan 1 boundary.
    if initial_mode and old_count >= CONSECUTIVE_OLD_REQUIRED:
        state["initial_backfill_complete"] = True

    save_state(
        state
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("RUN COMPLETE")
    print("=" * 60)

    print(
        "Successful:",
        successful,
    )

    print(
        "Failed:",
        failed,
    )

    print(
        "Old/out of range:",
        old_count,
    )

    print(
        "No date:",
        no_date,
    )

    print(
        "New/updated articles:",
        len(new_articles),
    )

    print(
        "Total stored articles:",
        len(merged),
    )

    print(
        "Initial backfill complete:",
        state["initial_backfill_complete"],
    )

    print()
    print(
        "Saved:",
        OUTPUT_FILE,
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    run()