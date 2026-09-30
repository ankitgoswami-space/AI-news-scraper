import json
import requests
from bs4 import BeautifulSoup

url = "https://techcrunch.com/category/artificial-intelligence/"

response = requests.get(
    url,
    headers={
        "User-Agent": "Mozilla/5.0"
    }
)

print("Status code:", response.status_code)

soup = BeautifulSoup(response.text, "html.parser")

print("Page title:", soup.title.get_text(strip=True))

headings = soup.find_all(["h1", "h2", "h3"])

news = []

for heading in headings:
    text = heading.get_text(" ", strip=True)
    link = heading.find("a")

    if link:
        href = link.get("href")

        if href and "/2026/" in href:
            article = {
                "title": text,
                "url": href,
                "source": "TechCrunch",
                "category": "AI"
            }

            news.append(article)

unique_news = []
seen_urls = set()

for article in news:
    if article["url"] not in seen_urls:
        unique_news.append(article)
        seen_urls.add(article["url"])

print("Unique articles:", len(unique_news))

with open("../data/news.json", "w", encoding="utf-8") as file:
    json.dump(unique_news, file, ensure_ascii=False, indent=4)

print("News saved to data/news.json")