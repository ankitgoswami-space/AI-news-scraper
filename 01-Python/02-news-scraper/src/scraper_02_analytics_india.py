import json
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

SITEMAP_URL = "https://analyticsindiamag.com/ai-news-sitemap.xml"
MAX_ARTICLES = 15

# Project root:
# 02-news-scraper/
PROJECT_ROOT = Path(__file__).resolve().parent.parent

OUTPUT_FILE = PROJECT_ROOT / "data" / "analytics_india.json"


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    )
}


# --------------------------------------------------
# GET ARTICLE URLS
# --------------------------------------------------

def get_article_urls():
    print("Fetching sitemap...")

    response = requests.get(
        SITEMAP_URL,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "xml")

    urls = []

    for url_tag in soup.find_all("url"):
        loc = url_tag.find("loc")

        if loc:
            url = loc.get_text(strip=True)

            if url not in urls:
                urls.append(url)

    return urls[:MAX_ARTICLES]


# --------------------------------------------------
# EXTRACT ARTICLE
# --------------------------------------------------

def extract_article(page, url):
    try:
        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000
        )

        # Allow React content to render
        page.wait_for_timeout(4000)

        content = page.locator("body").inner_text().strip()

        # Sometimes AIM needs a little more time
        if len(content) < 500:
            print(
                f"Low content ({len(content)} chars) - waiting and retrying..."
            )

            page.wait_for_timeout(5000)

            content = page.locator("body").inner_text().strip()

        # One final reload for pages that did not render
        if len(content) < 500:
            print("Retrying page reload...")

            page.reload(
                wait_until="domcontentloaded",
                timeout=60000
            )

            page.wait_for_timeout(5000)

            content = page.locator("body").inner_text().strip()

        if len(content) < 500:
            print(
                f"FAILED: only {len(content)} characters extracted"
            )
            return None

        # Extract article title
        title_locator = page.locator("h1").first

        if title_locator.count() > 0:
            title = title_locator.inner_text().strip()
        else:
            title = page.title().strip()

        return {
            "title": title,
            "source": "Analytics India Magazine",
            "url": url,
            "content": content
        }

    except Exception as error:
        print(f"ERROR: {error}")
        return None


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():

    print("Analytics India Magazine scraper")
    print("--------------------------------")

    # Get small batch of fresh candidates
    article_urls = get_article_urls()

    print("Fresh candidates found:", len(article_urls))
    print("Articles selected:", len(article_urls))

    articles = []

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            viewport={
                "width": 1366,
                "height": 900
            },
            user_agent=HEADERS["User-Agent"]
        )

        for index, url in enumerate(article_urls, start=1):

            print(f"\n[{index}/{len(article_urls)}]")
            print(url)

            article = extract_article(page, url)

            if article:

                print(
                    "Extracted characters:",
                    len(article["content"])
                )

                articles.append(article)

            else:
                print("Skipped: article content not available")

            # Small delay between pages
            time.sleep(1)

        browser.close()

    # --------------------------------------------------
    # SAVE RESULT
    # --------------------------------------------------

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            articles,
            file,
            ensure_ascii=False,
            indent=4
        )

    print("\n--------------------------------")
    print("Extraction complete")
    print("Successful articles:", len(articles))
    print("Selected candidates:", len(article_urls))
    print("Output:", OUTPUT_FILE)


if __name__ == "__main__":
    main()