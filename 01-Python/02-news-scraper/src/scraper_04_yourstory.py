"""
YourStory RSS scraper.

Usage:
    python scraper_04_yourstory.py
    python scraper_04_yourstory.py --audit
"""

from rss_common import main_for

CONFIG = {
    "source_name": "YourStory",
    "feed_url": "https://yourstory.com/feed",
    "output_file": "yourstory.json",
    "log_file": "yourstory.log",
}

if __name__ == "__main__":
    main_for(CONFIG)