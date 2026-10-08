"""
V4 LLM Enricher — Gemini Flash Lite

Reads the AIM articles and enriches each one with structured fields
produced by an LLM:
  - summary          (1-2 sentence plain-English summary)
  - companies        (list of organizations mentioned)
  - technologies     (list of AI models, chips, frameworks mentioned)
  - skills           (list of concrete technical skills from a closed list)
  - category         (Funding | Policy | AI Startup | AI Research | Career | AI Product | Other)

Features:
  - Gemini primary (fast + cheap + high daily limit)
  - Retry with backoff on 503/429
  - Checkpoint every N articles
  - Resume-safe: re-run continues from where it left off
  - Ctrl+C-safe: writes progress to disk on interrupt

Input:  data/analytics_india.json
Output: data/analytics_india_enriched.json

Usage:
    python llm_enricher.py                  # process all remaining
    python llm_enricher.py --limit 20       # process only 20 (for testing)
    python llm_enricher.py --reset          # start fresh (clear enriched file)
    python llm_enricher.py --audit          # show stats, no processing
"""

import argparse
import json
import os
import re
import time
from pathlib import Path

from google import genai


# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

INPUT_FILE = PROJECT_ROOT / "data" / "analytics_india.json"
OUTPUT_FILE = PROJECT_ROOT / "data" / "analytics_india_enriched.json"

MODEL = "gemini-flash-lite-latest"
CHECKPOINT_EVERY = 25          # save to disk every N articles
MAX_RETRIES = 4                # per-article retry attempts
CONTENT_CHARS = 2000           # trim article content before sending to LLM
RETRY_BACKOFF = 5              # seconds; multiplied by attempt number


# ============================================================
# LOAD ENV
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
    "You are an AI ecosystem analyst. You extract structured, deterministic "
    "data from news articles. Always respond with valid JSON only — no prose, "
    "no markdown fences. Follow the extraction rules exactly. Do not invent "
    "values that are not supported by the article text."
)

USER_TEMPLATE = """Analyze the article below and return a JSON object with exactly
these five keys: summary, companies, technologies, skills, category.

RULES:

1. summary
   - 1 to 2 sentences in plain English.
   - No marketing language. Just the essential facts.

2. companies
   - Names of companies, organizations, universities, or labs mentioned.
   - Use the most commonly recognized name (e.g. "OpenAI", not "Open AI Inc").
   - Empty array [] if none are found.

3. technologies
   - Specific AI models, systems, frameworks, chips, or platforms mentioned.
   - Examples: "GPT-4", "Llama 3", "Blackwell GPU", "Synopsys.ai".
   - DO NOT include generic words like "AI", "machine learning", "cloud".
   - Empty array [] if none are found.

4. skills
   - ONLY concrete technical skills from this exact allowed list:
     Python, JavaScript, TypeScript, Java, C++, Rust, Go, SQL,
     PyTorch, TensorFlow, JAX, scikit-learn, Keras, Hugging Face, Transformers,
     LLM, RAG, LangChain, LlamaIndex, Vector DB, Embeddings, Fine-tuning,
     Quantization, Prompt Engineering, Agentic AI, Multimodal, Diffusion, MoE,
     AWS, Azure, GCP, Docker, Kubernetes, MLOps, Git,
     Spark, Kafka, Airflow, Snowflake, Databricks, PostgreSQL, MongoDB
   - Use the EXACT names from this list. Do not invent new skills.
   - Empty array [] if no listed skill is mentioned.

5. category
   - Pick the FIRST rule that matches:
       1. "Funding"      if capital, funding round, valuation, raise, or IPO is mentioned.
       2. "Policy"       if government, regulation, policy, ministry, or bill is mentioned.
       3. "AI Startup"   if a startup is launching or entering a new area.
       4. "AI Research"  if a paper, study, benchmark, or research result is the focus.
       5. "Career"       if hiring, jobs, skills, or workforce is the focus.
       6. "AI Product"   if a company shipped, launched, or updated a product.
       7. "Other"        if none of the above applies.

Return ONLY the JSON object.

Title: {title}

Content: {content}
"""


# ============================================================
# HELPERS
# ============================================================

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


def load_json(path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  WARNING: Could not read {path}: {e}")
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
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    return f"{h}h {m}m"


# ============================================================
# LLM CALL
# ============================================================

def enrich_one(article):
    """
    Returns (parsed_dict, tokens_used) or raises after MAX_RETRIES.
    """
    prompt = SYSTEM_PROMPT + "\n\n" + USER_TEMPLATE.format(
        title=article.get("title", ""),
        content=(article.get("content", "") or "")[:CONTENT_CHARS],
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
            raw = resp.text
            parsed = parse_json_safe(raw)

            usage = getattr(resp, "usage_metadata", None)
            tokens = getattr(usage, "total_token_count", 0) if usage else 0

            if not parsed:
                raise ValueError(f"LLM returned unparseable JSON: {raw[:200]}")

            return parsed, tokens

        except Exception as exc:
            last_exc = exc
            msg = str(exc)
            transient = (
                "503" in msg or "UNAVAILABLE" in msg
                or "429" in msg or "RESOURCE_EXHAUSTED" in msg
                or "500" in msg or "INTERNAL" in msg
            )
            if transient and attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF * attempt
                print(f"      [retry {attempt}/{MAX_RETRIES - 1}] "
                      f"waiting {wait}s — {msg[:80]}")
                time.sleep(wait)
                continue
            raise

    raise last_exc


# ============================================================
# MAIN PROCESSING
# ============================================================

def process(limit=0):
    if not INPUT_FILE.exists():
        print(f"ERROR: input file not found: {INPUT_FILE}")
        return

    articles = load_json(INPUT_FILE, [])
    if not isinstance(articles, list):
        print("ERROR: input file is not a list")
        return

    print(f"Input articles : {len(articles)}")

    # Load existing enriched output (for resume)
    enriched = load_json(OUTPUT_FILE, [])
    if not isinstance(enriched, list):
        enriched = []

    done_urls = {a.get("url") for a in enriched if a.get("url")}
    print(f"Already done   : {len(done_urls)}")

    todo = [a for a in articles if a.get("url") and a["url"] not in done_urls]
    print(f"Remaining      : {len(todo)}")

    if limit > 0:
        todo = todo[:limit]
        print(f"Limit applied  : processing only {len(todo)}")

    if not todo:
        print("Nothing to do. All articles are already enriched.")
        return

    print(f"Model          : {MODEL}")
    print()

    # Stats
    start_time = time.time()
    total_tokens = 0
    processed = 0
    failed = 0

    try:
        for i, art in enumerate(todo, start=1):
            title = (art.get("title") or "")[:70]
            print(f"[{i}/{len(todo)}] {title}")

            try:
                parsed, tokens = enrich_one(art)
            except Exception as exc:
                failed += 1
                print(f"      FAILED: {type(exc).__name__}: {str(exc)[:100]}")
                # store the article without enrichment so we don't loop forever
                enriched.append({
                    **art,
                    "summary": "",
                    "companies": [],
                    "technologies": [],
                    "skills": [],
                    "category": "",
                    "_enrichment_error": str(exc)[:200],
                })
                continue

            def clean_list(lst):
                if not isinstance(lst, list):
                    return []
                return [str(x).strip() for x in lst if str(x).strip()]

            enriched.append({
                **art,
                "summary": (parsed.get("summary") or "").strip(),
                "companies": clean_list(parsed.get("companies")),
                "technologies": clean_list(parsed.get("technologies")),
                "skills": clean_list(parsed.get("skills")),
                "category": (parsed.get("category") or "").strip(),
            })

            processed += 1
            total_tokens += tokens

            # Progress line
            elapsed = time.time() - start_time
            avg = elapsed / i
            remaining = (len(todo) - i) * avg
            print(
                f"      {tokens:>5} tok  |  "
                f"{processed} ok, {failed} fail  |  "
                f"ETA {format_eta(remaining)}"
            )

            # Checkpoint
            if i % CHECKPOINT_EVERY == 0:
                save_json(OUTPUT_FILE, enriched)
                print(f"      >>> checkpoint saved ({len(enriched)} total)")

    except KeyboardInterrupt:
        print("\n\nInterrupted by user (Ctrl+C). Saving progress...")

    finally:
        save_json(OUTPUT_FILE, enriched)

        elapsed = time.time() - start_time
        print()
        print("=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Articles processed : {processed}")
        print(f"Articles failed    : {failed}")
        print(f"Total enriched     : {len(enriched)}")
        print(f"Total tokens used  : {total_tokens:,}")
        print(f"Time elapsed       : {format_eta(elapsed)}")
        if processed > 0:
            print(f"Avg per article    : {elapsed / processed:.1f}s")
            print(f"Avg tokens/article : {total_tokens / processed:.0f}")
        print(f"Output saved       : {OUTPUT_FILE}")


# ============================================================
# AUDIT
# ============================================================

def audit():
    enriched = load_json(OUTPUT_FILE, [])
    if not enriched:
        print("No enriched data yet.")
        return

    print()
    print("=" * 60)
    print("ENRICHED DATA AUDIT")
    print("=" * 60)
    print(f"Total enriched     : {len(enriched)}")

    with_summary = sum(1 for a in enriched if a.get("summary"))
    with_companies = sum(1 for a in enriched if a.get("companies"))
    with_tech = sum(1 for a in enriched if a.get("technologies"))
    with_skills = sum(1 for a in enriched if a.get("skills"))
    with_error = sum(1 for a in enriched if a.get("_enrichment_error"))

    print(f"With summary       : {with_summary} ({with_summary*100//len(enriched)}%)")
    print(f"With companies     : {with_companies} ({with_companies*100//len(enriched)}%)")
    print(f"With technologies  : {with_tech} ({with_tech*100//len(enriched)}%)")
    print(f"With skills        : {with_skills} ({with_skills*100//len(enriched)}%)")
    print(f"With errors        : {with_error}")

    # Category distribution
    cats = {}
    for a in enriched:
        c = a.get("category") or "UNKNOWN"
        cats[c] = cats.get(c, 0) + 1

    print()
    print("Category distribution:")
    for c, n in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"  {c:15s} : {n}")

    # Top companies
    company_counts = {}
    for a in enriched:
        for co in a.get("companies") or []:
            company_counts[co] = company_counts.get(co, 0) + 1

    print()
    print("Top 15 companies:")
    for co, n in sorted(company_counts.items(), key=lambda x: -x[1])[:15]:
        print(f"  {co:30s} : {n}")

    # Top skills
    skill_counts = {}
    for a in enriched:
        for s in a.get("skills") or []:
            skill_counts[s] = skill_counts.get(s, 0) + 1

    print()
    print("Top 15 skills (LLM-extracted):")
    for s, n in sorted(skill_counts.items(), key=lambda x: -x[1])[:15]:
        print(f"  {s:20s} : {n}")


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="V4 LLM enricher")
    parser.add_argument("--limit", type=int, default=0,
                        help="process only N articles (0 = all remaining)")
    parser.add_argument("--reset", action="store_true",
                        help="delete existing enriched file and start fresh")
    parser.add_argument("--audit", action="store_true",
                        help="print stats on enriched output and exit")
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