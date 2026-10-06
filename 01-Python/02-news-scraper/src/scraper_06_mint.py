"""
Mint (Technology) RSS scraper.

The Mint RSS feed serves only a short teaser, so this scraper fetches
each article's full body from the page HTML.

Usage:
    python scraper_06_mint.py
    python scraper_06_mint.py --audit
"""

from rss_common import main_for

CONFIG = {
    "source_name": "Mint - Technology",
    "feed_url": "https://www.livemint.com/rss/technology",
    "output_file": "mint.json",
    "log_file": "mint.log",
    "fetch_full_content": True,
    "content_selectors": ["div.storyContent"],
}

if __name__ == "__main__":
    main_for(CONFIG)