# Indian AI Career & Startup News Monitor

Scrape AI-related news from TechCrunch using Python and BeautifulSoup, and save the extracted articles as structured JSON data.

## What This Project Does

This project demonstrates the basic workflow of web scraping:

1. Requests — Fetches the TechCrunch AI category page
2. BeautifulSoup — Parses the HTML
3. HTML element discovery — Finds relevant article headings and links
4. Data extraction — Extracts article titles and URLs
5. Duplicate removal — Removes duplicate articles using URLs
6. JSON — Saves the structured news data

The long-term goal is to build a personal monitor for:

- Indian AI startups
- AI job opportunities
- Skill requirements
- AI developments
- New research and findings
- AI ecosystem activity in Bengaluru, Hyderabad, Gurgaon/Gurugram and Noida

The current version focuses only on the web-scraping foundation.

## Files

| File | Purpose |
|---|---|
| scraper.py | Scrapes the TechCrunch AI category page using Requests and BeautifulSoup |
| news.json | Stores the extracted and deduplicated article data |
| PROJECT_OVERVIEW.md | Full project scope, roadmap and development plan |

## Requirements

- Python 3.10+
- Python packages: requests, beautifulsoup4

## Setup

### 1. Install Python Packages

pip install requests beautifulsoup4

### 2. Run the Scraper

From the src directory:

python scraper.py

The extracted news data is saved to:

data/news.json

## Current Result

The current scraper extracts 36 unique AI articles from the fetched TechCrunch AI category page.

Each article contains:

title
url
source
category

## What I Learned

- How HTTP requests work with Python
- How to fetch HTML using requests
- How to parse HTML using BeautifulSoup
- How to inspect HTML structure before choosing selectors
- How to use find_all() to locate HTML elements
- How to extract text from HTML elements
- How to extract links using href
- How to create structured Python dictionaries
- How to use sets for duplicate detection
- How to save structured data as JSON
- Why a successful HTTP request does not guarantee that the expected HTML tags are present

## Future Improvements

- Add more news sources
- Extract publication dates
- Improve article filtering
- Add location/category filtering
- Extract companies, job roles and skill requirements
- Track Indian AI startups
- Add AI-based summarization
- Build a career-intelligence layer using LLMs and RAG

## Author

**Ankit Goswami**
Gen AI Engineer Journey (2026)