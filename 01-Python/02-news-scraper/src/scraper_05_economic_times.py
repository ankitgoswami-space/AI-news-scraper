"""
Economic Times (Tech) RSS scraper.

The ET RSS feed serves only a short teaser, so this scraper fetches
each article's full body from the page HTML.

Usage:
    python scraper_05_economic_times.py
    python scraper_05_economic_times.py --audit
"""

from rss_common import main_for

CONFIG = {
    "source_name": "Economic Times - Tech",
    "feed_url": "https://economictimes.indiatimes.com/tech/rssfeeds/13357270.cms",
    "output_file": "economic_times.json",
    "log_file": "economic_times.log",
    "fetch_full_content": True,
    "content_selectors": ["div.articleBody", "article"],
}

if __name__ == "__main__":
    main_for(CONFIG)