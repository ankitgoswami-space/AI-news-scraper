"""
Google Research blog RSS scraper.

The RSS feed only serves a tiny snippet, so this scraper fetches each
article's full body from the page HTML.

Usage:
    python scraper_13_google_research.py
    python scraper_13_google_research.py --audit
"""

from rss_common import main_for

CONFIG = {
    "source_name": "Google Research",
    "feed_url": "https://research.google/blog/rss/",
    "output_file": "google_research.json",
    "log_file": "google_research.log",
    "fetch_full_content": True,
    "content_selectors": ["main article", "article", "main"],
}

if __name__ == "__main__":
    main_for(CONFIG)