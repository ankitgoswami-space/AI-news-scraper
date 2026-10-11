"""
Adzuna Job Enricher — V4 extension for real job listings.

For each Adzuna job:
  1. Fetch the full job description page (Adzuna details URL)
  2. Send it to Gemini
  3. Extract structured fields

Fixes (2026-10-11):
  - Adzuna fetch retry on connection errors
  - 404 marked permanent (never retried)
  - Connection/429 marked temporary (retried next run)
  - Slow down when Adzuna blocks

Usage:
    python adzuna_enricher.py --limit 10
    python adzuna_enricher.py
    python adzuna_enricher.py --reset
    python adzuna_enricher.py --audit
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

INPUT_FILE = DATA_DIR / "adzuna.json"
OUTPUT_FILE = DATA_DIR / "adzuna_enriched.json"

MODEL = "gemini-flash-lite-latest"
CHECKPOINT_EVERY = 25
MAX_RETRIES = 4
RETRY_BACKOFF = 5
CONTENT_CHARS = 4000
FETCH_DELAY = 0.5
CONTENT_SELECTOR = "main"

# Adzuna block handling
ADZUNA_FETCH_RETRIES = 3        # for each job page fetch
ADZUNA_RETRY_WAIT = 5           # seconds; multiplied by attempt
ADZUNA_BLOCK_COOLDOWN = 60      # if >= N consecutive connection errors, pause
ADZUNA_BLOCK_THRESHOLD = 5

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
# ERROR CLASSIFIERS
# ============================================================

def is_permanent_error(exc):
    """404 / Gone = job deleted, never retry."""
    msg = str(exc)
    return "404" in msg or "Not Found" in msg or "410" in msg or "Gone" in msg


def is_connection_error(exc):
    """Network errors — temporary, retry next run."""
    msg = str(exc).lower()
    return (
        "connection" in msg
        or "max retries" in msg
        or "10054" in msg
        or "timeout" in msg
        or "readerror" in msg
        or "connectionerror" in msg
    )


def is_transient_llm_error(exc):
    """429/503 — retry immediately with backoff."""
    msg = str(exc)
    return (
        "429" in msg or "RESOURCE_EXHAUSTED" in msg
        or "503" in msg or "UNAVAILABLE" in msg
        or "500" in msg
    )


# ============================================================
# PROMPT
# ============================================================

SYSTEM_PROMPT = (
    "You are a job market analyst. You read real job postings and extract "
    "structured, deterministic data. Always respond with valid JSON only — "
    "no prose, no markdown fences. Do not invent values that are not supported "
    "by the posting text."
)

USER_TEMPLATE = """Analyze this job posting and return a JSON object with EXACTLY
these keys: role_category, experience_min_years, experience_max_years,
experience_level, employment_type, remote_type, salary_range_lpa,
required_skills, nice_to_have_skills, responsibilities_summary.

RULES:

1. role_category — one of:
   "AI/ML Engineer", "Data Scientist", "Data Engineer", "MLOps Engineer",
   "AI Research", "AI Product Manager", "Frontend Engineer", "Backend Engineer",
   "Full Stack Engineer", "DevOps Engineer", "Other"

2. experience_min_years — integer (minimum years) or null
3. experience_max_years — integer (maximum years) or null
4. experience_level — one of: "fresher", "junior", "mid", "senior", "lead", "unknown"
5. employment_type — one of: "full-time", "part-time", "contract", "internship", "unknown"
6. remote_type — one of: "remote", "hybrid", "onsite", "unknown"
7. salary_range_lpa — string like "15-25" or "20+" or "" if not mentioned

8. required_skills — array of ONLY these exact names:
   Python, JavaScript, TypeScript, Java, C++, Rust, Go, SQL,
   PyTorch, TensorFlow, JAX, scikit-learn, Keras, Hugging Face, Transformers,
   LLM, RAG, LangChain, LlamaIndex, Vector DB, Embeddings, Fine-tuning,
   Quantization, Prompt Engineering, Agentic AI, Multimodal, Diffusion, MoE,
   AWS, Azure, GCP, Docker, Kubernetes, MLOps, Git, Linux,
   Spark, Kafka, Airflow, Snowflake, Databricks, PostgreSQL, MongoDB,
   React, Node.js, FastAPI, Django, Flask, REST API, GraphQL,
   Computer Vision, NLP, Deep Learning, Machine Learning, Data Analysis,
   Pandas, NumPy

9. nice_to_have_skills — same closed list, only if "nice to have/preferred/bonus"

10. responsibilities_summary — 1-2 sentences

Return ONLY the JSON object.

Job Title: {title}
Company: {company}
Location: {location}

Full Description:
---
{content}
---
"""


# ============================================================
# HELPERS
# ============================================================

def fetch_job_page(url, retries=ADZUNA_FETCH_RETRIES):
    """Fetch full job description with retry. Raises on 404 or after retries."""
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
            # 404 → permanent, raise immediately
            if resp.status_code == 404:
                raise requests.HTTPError(f"404 Not Found: {url}", response=resp)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            el = soup.select_one(CONTENT_SELECTOR)
            if not el:
                return ""
            text = el.get_text(" ", strip=True)
            return re.sub(r"\s+", " ", text).strip()

        except requests.HTTPError as he:
            # 404 → permanent, don't retry
            if he.response is not None and he.response.status_code == 404:
                raise
            last_exc = he
            if attempt < retries:
                time.sleep(ADZUNA_RETRY_WAIT * attempt)
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(ADZUNA_RETRY_WAIT * attempt)

    raise last_exc


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


def clean_list(lst):
    if not isinstance(lst, list):
        return []
    return [str(x).strip() for x in lst if str(x).strip()]


def load_json(path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    temp = path.with_suffix(".tmp")
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    temp.replace(path)


def format_eta(seconds):
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"


# ============================================================
# LLM EXTRACTION
# ============================================================

def extract_from_llm(job, content):
    prompt = SYSTEM_PROMPT + "\n\n" + USER_TEMPLATE.format(
        title=job.get("title", ""),
        company=job.get("company", ""),
        location=job.get("location", ""),
        content=content[:CONTENT_CHARS],
    )

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
            if is_transient_llm_error(exc) and attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF * attempt
                print(f"      [llm retry {attempt}] {wait}s — {str(exc)[:70]}")
                time.sleep(wait)
                continue
            raise
    raise last_exc


# ============================================================
# PROCESS ONE JOB
# ============================================================

def enrich_job(job):
    """Returns (enriched_dict, tokens_used) or raises."""
    url = job.get("url", "")
    if not url:
        raise ValueError("no URL")

    content = fetch_job_page(url)
    if not content or len(content) < 200:
        raise ValueError(f"full content too short ({len(content)} chars)")

    parsed, tokens = extract_from_llm(job, content)

    return {
        **job,
        "role_category": parsed.get("role_category", "") or "",
        "experience_min_years": parsed.get("experience_min_years"),
        "experience_max_years": parsed.get("experience_max_years"),
        "experience_level": parsed.get("experience_level", "") or "",
        "employment_type": parsed.get("employment_type", "") or "",
        "remote_type": parsed.get("remote_type", "") or "",
        "salary_range_lpa": parsed.get("salary_range_lpa", "") or "",
        "required_skills": clean_list(parsed.get("required_skills")),
        "nice_to_have_skills": clean_list(parsed.get("nice_to_have_skills")),
        "responsibilities_summary": parsed.get("responsibilities_summary", "") or "",
        "_full_description_chars": len(content),
    }, tokens


# ============================================================
# MAIN
# ============================================================

def process(limit=0):
    if not INPUT_FILE.exists():
        print(f"ERROR: input not found: {INPUT_FILE}")
        return

    jobs = load_json(INPUT_FILE, [])
    if not isinstance(jobs, list):
        print("ERROR: input is not a list")
        return

    print(f"Input jobs     : {len(jobs)}")

    enriched = load_json(OUTPUT_FILE, [])
    if not isinstance(enriched, list):
        enriched = []

    # Skip: successfully enriched OR permanently failed (404)
    # Retry: temporary failures (connection, 429) and untouched jobs
    done_urls = set()
    for j in enriched:
        url = j.get("url")
        if not url:
            continue
        # Skip only if successfully enriched OR permanently failed
        has_error = bool(j.get("_enrichment_error"))
        is_permanent = bool(j.get("_permanent_failure"))
        is_temporary = bool(j.get("_temporary_failure"))

        if not has_error and not is_temporary:
            done_urls.add(url)          # success
        elif is_permanent:
            done_urls.add(url)          # 404, skip forever
        # else: retry (temporary failure, or old-format error without flags)
    print(f"Already done   : {len(done_urls)}")

    todo = [j for j in jobs if j.get("url") and j["url"] not in done_urls]
    print(f"Remaining      : {len(todo)}")

    if limit > 0:
        todo = todo[:limit]
        print(f"Limit applied  : {len(todo)}")

    if not todo:
        print("Nothing to do.")
        return

    print(f"Model          : {MODEL}")
    print()

    start_time = time.time()
    total_tokens = 0
    processed = 0
    failed_perm = 0
    failed_temp = 0
    consecutive_conn_errors = 0

    try:
        for i, job in enumerate(todo, start=1):
            title = (job.get("title") or "")[:65]
            print(f"[{i}/{len(todo)}] {title}")

            try:
                enriched_job, tokens = enrich_job(job)
                enriched.append(enriched_job)
                processed += 1
                total_tokens += tokens
                consecutive_conn_errors = 0

                elapsed = time.time() - start_time
                avg = elapsed / i
                eta = (len(todo) - i) * avg
                print(
                    f"      {tokens:>5} tok  |  "
                    f"{enriched_job['role_category']:20s} |  "
                    f"exp {enriched_job['experience_min_years']}-{enriched_job['experience_max_years']}  |  "
                    f"ETA {format_eta(eta)}"
                )

            except Exception as exc:
                if is_permanent_error(exc):
                    failed_perm += 1
                    print(f"      PERMANENT (skip forever): {str(exc)[:80]}")
                    enriched.append({
                        **job,
                        "_enrichment_error": str(exc)[:200],
                        "_permanent_failure": True,
                    })
                elif is_connection_error(exc):
                    failed_temp += 1
                    consecutive_conn_errors += 1
                    print(f"      TEMP (connection): {str(exc)[:80]}")
                    enriched.append({
                        **job,
                        "_enrichment_error": str(exc)[:200],
                        "_temporary_failure": True,
                    })
                else:
                    failed_temp += 1
                    print(f"      TEMP ({type(exc).__name__}): {str(exc)[:80]}")
                    enriched.append({
                        **job,
                        "_enrichment_error": str(exc)[:200],
                        "_temporary_failure": True,
                    })

            # Cooldown if Adzuna is blocking us
            if consecutive_conn_errors >= ADZUNA_BLOCK_THRESHOLD:
                print(f"      !!! {consecutive_conn_errors} consecutive connection errors — pausing {ADZUNA_BLOCK_COOLDOWN}s")
                time.sleep(ADZUNA_BLOCK_COOLDOWN)
                consecutive_conn_errors = 0

            if i % CHECKPOINT_EVERY == 0:
                save_json(OUTPUT_FILE, enriched)
                print(f"      >>> checkpoint saved ({len(enriched)} total)")

            time.sleep(FETCH_DELAY)

    except KeyboardInterrupt:
        print("\n\nInterrupted. Saving progress...")

    finally:
        save_json(OUTPUT_FILE, enriched)
        elapsed = time.time() - start_time

        print()
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Processed         : {processed}")
        print(f"Failed permanent  : {failed_perm} (404 — will NOT retry)")
        print(f"Failed temporary  : {failed_temp} (connection/LLM — will retry)")
        print(f"Total in file     : {len(enriched)}")
        print(f"Tokens used       : {total_tokens:,}")
        print(f"Time              : {format_eta(elapsed)}")
        if processed:
            print(f"Avg per job       : {elapsed/processed:.1f}s")
            print(f"Avg tokens        : {total_tokens/processed:.0f}")
        print(f"Output            : {OUTPUT_FILE}")


# ============================================================
# AUDIT
# ============================================================

def audit():
    data = load_json(OUTPUT_FILE, [])
    if not data:
        print("No enriched data yet.")
        return

    print()
    print("=" * 60)
    print("ADZUNA ENRICHED AUDIT")
    print("=" * 60)
    print(f"Total records      : {len(data)}")

    success = sum(1 for j in data if not j.get("_enrichment_error"))
    perm_fail = sum(1 for j in data if j.get("_permanent_failure"))
    temp_fail = sum(1 for j in data if j.get("_temporary_failure"))
    other_fail = len(data) - success - perm_fail - temp_fail

    print(f"Success            : {success}")
    print(f"Failed (permanent) : {perm_fail}")
    print(f"Failed (temporary) : {temp_fail}")
    print(f"Other failures     : {other_fail}")

    # Success-only stats
    ok = [j for j in data if not j.get("_enrichment_error")]
    if ok:
        with_skills = sum(1 for j in ok if j.get("required_skills"))
        with_salary = sum(1 for j in ok if j.get("salary_range_lpa"))
        with_exp = sum(1 for j in ok if j.get("experience_min_years") is not None)
        print(f"With skills        : {with_skills}")
        print(f"With salary        : {with_salary}")
        print(f"With experience    : {with_exp}")

        cats = {}
        for j in ok:
            c = j.get("role_category") or "UNKNOWN"
            cats[c] = cats.get(c, 0) + 1
        print()
        print("Role categories:")
        for c, n in sorted(cats.items(), key=lambda x: -x[1])[:12]:
            print(f"  {c:25s} : {n}")

        skills = {}
        for j in ok:
            for s in j.get("required_skills") or []:
                skills[s] = skills.get(s, 0) + 1
        print()
        print("Top required skills:")
        for s, n in sorted(skills.items(), key=lambda x: -x[1])[:15]:
            print(f"  {s:20s} : {n}")


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Adzuna enricher")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()

    if args.reset and OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()
        print(f"Removed {OUTPUT_FILE}")

    if args.audit:
        audit()
        return

    process(limit=args.limit)


if __name__ == "__main__":
    main()