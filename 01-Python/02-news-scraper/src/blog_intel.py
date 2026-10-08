"""
Blog intelligence extractor — V4 helper.

Fetches a curated blog post (BuildFastWithAI salary guide) and uses
Gemini to extract structured market intelligence:
  - Salary bands by role and experience
  - Skills in demand
  - City-wise patterns
  - Key insights

Output: data/market_intel.json

Usage:
    python blog_intel.py
    python blog_intel.py --url <custom_url>
    python blog_intel.py --audit
"""

import argparse
import json
import os
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from google import genai


# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_FILE = DATA_DIR / "market_intel.json"

DEFAULT_URL = "https://www.buildfastwithai.com/blogs/ai-jobs-india-salary-2026"
DEFAULT_TITLE = "AI Jobs in India Salary (2026): Complete Pay Guide"
CONTENT_SELECTOR = "div.prose"

MODEL = "gemini-flash-lite-latest"
MAX_RETRIES = 4
RETRY_BACKOFF = 5

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"}


# ============================================================
# LOAD ENV + CLIENT
# ============================================================

if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.getenv("GEMINI_API_KEY", "")
if not API_KEY:
    print("ERROR: GEMINI_API_KEY not set in .env")
    raise SystemExit(1)

client = genai.Client(api_key=API_KEY)


# ============================================================
# PROMPT
# ============================================================

SYSTEM_PROMPT = (
    "You are a labor-market analyst. You read long-form articles about "
    "AI jobs and salaries, and you extract structured, deterministic data. "
    "Always respond with valid JSON only — no prose, no markdown fences."
)

USER_TEMPLATE = """Read this blog post about AI jobs and salaries in India (2026)
and extract structured intelligence. Return a JSON object with EXACTLY these
five keys:

{{
  "salary_bands": [
    {{
      "role": "role title as written",
      "experience": "one of: fresher, junior, mid, senior, lead",
      "min_lpa": integer (or null if not mentioned),
      "max_lpa": integer (or null if not mentioned),
      "notes": "short note if the article gives specific context"
    }}
  ],
  "skills_in_demand": [
    {{
      "skill": "exact skill name (e.g. Python, PyTorch, RAG, LangChain)",
      "relevance": "one of: core, important, bonus",
      "notes": "short note if article gives context"
    }}
  ],
  "city_patterns": [
    {{
      "city": "city name",
      "typical_roles": ["role1", "role2"],
      "salary_range_lpa": "e.g. 13-35 LPA"
    }}
  ],
  "key_insights": [
    "bullet point 1",
    "bullet point 2"
  ],
  "article_meta": {{
    "title": "article title",
    "source_url": "article URL",
    "scraped_date": "YYYY-MM-DD"
  }}
}}

RULES:
- Only use information actually present in the article. Do NOT invent.
- If a field has no data, return an empty array.
- Use exact role names as written in the article.
- Salary numbers in LPA (lakhs per annum) as integers, no commas.
- Skills must be concrete technical skills, not soft skills.
- Key insights should be 5-10 short bullet points capturing the article's
  main factual claims.

Article:
---
{content}
---

Return ONLY the JSON object."""


# ============================================================
# HELPERS
# ============================================================

def fetch_blog(url):
    resp = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    el = soup.select_one(CONTENT_SELECTOR)
    if not el:
        raise RuntimeError(f"Selector '{CONTENT_SELECTOR}' not found on page")
    text = el.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text


def parse_json_safe(text):
    if not text:
        return None
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        return None


def save_json(path, data):
    temp = path.with_suffix(".tmp")
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    temp.replace(path)


def load_json(path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


# ============================================================
# LLM EXTRACTION
# ============================================================

def extract(content):
    prompt = SYSTEM_PROMPT + "\n\n" + USER_TEMPLATE.format(content=content)

    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config={
                    "temperature": 0.1,
                    "response_mime_type": "application/json",
                },
            )
            parsed = parse_json_safe(resp.text)
            usage = getattr(resp, "usage_metadata", None)
            tokens = getattr(usage, "total_token_count", 0) if usage else 0

            if not parsed:
                raise ValueError(f"Unparseable JSON: {resp.text[:200]}")
            return parsed, tokens

        except Exception as exc:
            last_exc = exc
            msg = str(exc)
            transient = ("503" in msg or "UNAVAILABLE" in msg
                         or "429" in msg or "RESOURCE_EXHAUSTED" in msg)
            if transient and attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF * attempt
                print(f"  [retry {attempt}] waiting {wait}s — {msg[:80]}")
                time.sleep(wait)
                continue
            raise
    raise last_exc


# ============================================================
# RUN
# ============================================================

def run(url, title):
    print()
    print("=" * 60)
    print("BLOG INTELLIGENCE EXTRACTOR")
    print("=" * 60)
    print(f"URL   : {url}")
    print(f"Model : {MODEL}")
    print()

    print("Fetching blog...")
    content = fetch_blog(url)
    print(f"Extracted {len(content):,} chars from '{CONTENT_SELECTOR}'")
    print()

    print("Sending to Gemini for structured extraction...")
    start = time.time()
    parsed, tokens = extract(content)
    elapsed = time.time() - start

    print(f"Done in {elapsed:.1f}s | {tokens:,} tokens used")
    print()

    # Attach meta if missing
    if "article_meta" not in parsed or not isinstance(parsed.get("article_meta"), dict):
        parsed["article_meta"] = {}
    parsed["article_meta"].setdefault("title", title)
    parsed["article_meta"].setdefault("source_url", url)
    parsed["article_meta"].setdefault("scraped_date",
                                      time.strftime("%Y-%m-%d"))

    # Merge with existing market_intel.json (keep list of articles)
    existing = load_json(OUTPUT_FILE, {})
    if not isinstance(existing, dict):
        existing = {}

    articles = existing.get("articles", [])
    # Replace by URL
    articles = [a for a in articles if a.get("article_meta", {}).get("source_url") != url]
    articles.append(parsed)

    output = {
        "generated_by": "blog_intel.py",
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "articles": articles,
    }
    save_json(OUTPUT_FILE, output)

    # Print summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Salary bands   : {len(parsed.get('salary_bands', []))}")
    print(f"Skills         : {len(parsed.get('skills_in_demand', []))}")
    print(f"City patterns  : {len(parsed.get('city_patterns', []))}")
    print(f"Key insights   : {len(parsed.get('key_insights', []))}")
    print()
    print(f"Saved: {OUTPUT_FILE}")

    # Quick preview
    print()
    print("--- Salary bands preview ---")
    for b in parsed.get("salary_bands", [])[:8]:
        lo = b.get("min_lpa")
        hi = b.get("max_lpa")
        rng = f"{lo}-{hi} LPA" if lo and hi else "n/a"
        print(f"  {b.get('role', '?')[:40]:40s} | {b.get('experience', '?'):8s} | {rng}")

    print()
    print("--- Skills preview ---")
    for s in parsed.get("skills_in_demand", [])[:12]:
        print(f"  {s.get('skill', '?'):25s} | {s.get('relevance', '?')}")


# ============================================================
# AUDIT
# ============================================================

def audit():
    data = load_json(OUTPUT_FILE, {})
    articles = data.get("articles", [])
    print()
    print("=" * 60)
    print("MARKET INTEL AUDIT")
    print("=" * 60)
    print(f"Articles stored : {len(articles)}")
    for a in articles:
        meta = a.get("article_meta", {})
        print(f"  - {meta.get('title', '?')[:60]}")
        print(f"    URL: {meta.get('source_url', '?')}")
        print(f"    salary_bands: {len(a.get('salary_bands', []))}, "
              f"skills: {len(a.get('skills_in_demand', []))}, "
              f"cities: {len(a.get('city_patterns', []))}")


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Blog intelligence extractor")
    parser.add_argument("--url", default=DEFAULT_URL, help="blog URL")
    parser.add_argument("--title", default=DEFAULT_TITLE, help="article title")
    parser.add_argument("--audit", action="store_true", help="show stored data")
    args = parser.parse_args()

    if args.audit:
        audit()
        return

    run(args.url, args.title)


if __name__ == "__main__":
    main()