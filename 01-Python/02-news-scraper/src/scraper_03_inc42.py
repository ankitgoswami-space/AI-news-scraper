"""
Inc42 RSS scraper.

Usage:
    python scraper_03_inc42.py
    python scraper_03_inc42.py --audit
"""

from rss_common import main_for

CONFIG = {
    "source_name": "Inc42",
    "feed_url": "https://inc42.com/feed/",
    "output_file": "inc42.json",
    "log_file": "inc42.log",
}

if __name__ == "__main__":
    main_for(CONFIG)