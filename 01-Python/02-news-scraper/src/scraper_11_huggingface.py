"""
Hugging Face scraper (REST API -> clean model JSON)

Usage:
    python scraper_11_huggingface.py                # default: multi-sort top 3000
    python scraper_11_huggingface.py --limit 2000   # cap
    python scraper_11_huggingface.py --incremental  # since last stored created_at
    python scraper_11_huggingface.py --sort trending  # trending only
    python scraper_11_huggingface.py --audit        # quality report, no fetching
"""

import argparse
import json
import logging
import re
import time
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path

import requests


# ============================================================
# CONFIG
# ============================================================

SOURCE_NAME = "Hugging Face"
API_URL = "https://huggingface.co/api/models"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

OUTPUT_FILE = DATA_DIR / "huggingface.json"
STATE_FILE = DATA_DIR / "huggingface_state.json"
LOG_FILE = DATA_DIR / "huggingface.log"

DEFAULT_LIMIT = 3000
HF_MAX_PER_REQUEST = 1000     # HF hard cap per request
REQUEST_DELAY = 1.0
MAX_RETRIES = 3

MIN_TAGS = 1

USER_AGENT = (
    "AI-Career-Intel-Project/0.1 "
    "(educational research; https://github.com/ankitgoswami-space/AI-news-scraper)"
)


# ============================================================
# LOGGING
# ============================================================

DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


# ============================================================
# HTTP SESSION
# ============================================================

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
)


# ============================================================
# BASIC HELPERS
# ============================================================

def parse_date_string(value):
    if not value:
        return None
    value = str(value).strip()
    match = re.search(r"(20\d{2})-(\d{1,2})-(\d{1,2})", value)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass
    return None


def normalize_model_url(model_id):
    if not model_id:
        return ""
    return f"https://huggingface.co/{model_id.strip().rstrip('/')}"


def derive_author(model_id, explicit_author):
    if explicit_author:
        return explicit_author
    if model_id and "/" in model_id:
        return model_id.split("/", 1)[0]
    return ""


def build_content(model):
    parts = []
    if model.get("pipeline_tag"):
        parts.append(f"Pipeline: {model['pipeline_tag']}")
    if model.get("library_name"):
        parts.append(f"Library: {model['library_name']}")
    tags = model.get("tags") or []
    if tags:
        parts.append("Tags: " + ", ".join(tags))
    return ". ".join(parts)


# ============================================================
# JSON HELPERS
# ============================================================

def load_json(path, default):
    if not path.exists():
        return deepcopy(default)
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as exc:
        logger.error("Could not read %s: %s", path, exc)
        return deepcopy(default)


def save_json(path, data):
    temp_path = path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    temp_path.replace(path)


# ============================================================
# STATE
# ============================================================

DEFAULT_STATE = {
    "last_run": None,
    "last_created_at": None,
}


def load_state():
    state = deepcopy(DEFAULT_STATE)
    loaded = load_json(STATE_FILE, {})
    if isinstance(loaded, dict):
        state.update(loaded)
    return state


def save_state(state):
    state["last_run"] = datetime.now().isoformat(timespec="seconds")
    save_json(STATE_FILE, state)


# ============================================================
# EXISTING DATA
# ============================================================

def load_existing_models():
    data = load_json(OUTPUT_FILE, [])
    return data if isinstance(data, list) else []


def merge_models(existing, new_models):
    by_id = {}
    for model in existing:
        mid = model.get("id")
        if mid:
            by_id[mid] = model
    for model in new_models:
        mid = model.get("id")
        if not mid:
            continue
        by_id[mid] = model
    result = list(by_id.values())
    result.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return result


# ============================================================
# FETCH
# ============================================================

def fetch_page(sort, limit=HF_MAX_PER_REQUEST, retries=MAX_RETRIES):
    """
    Fetch up to `limit` models sorted by `sort`.

    NOTE: HF API does NOT support offset pagination — the `start` param is
    ignored and every request returns the same top-N list. So we fetch a
    single page per sort and combine multiple sorts to broaden the result.
    """
    params = {
        "sort": sort,
        "direction": -1,
        "limit": limit,
    }

    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            resp = SESSION.get(API_URL, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            last_exc = exc
            logger.warning("HF fetch failed (%s/%s): %s", attempt, retries, exc)
            time.sleep(2 * attempt)

    raise last_exc


# ============================================================
# PARSE
# ============================================================

def parse_models(raw_models):
    models = []
    for raw in raw_models:
        try:
            model_id = raw.get("id") or raw.get("modelId")
            if not model_id:
                continue

            tags = raw.get("tags") or []
            if len(tags) < MIN_TAGS:
                continue

            created = parse_date_string(raw.get("createdAt"))
            if not created:
                continue

            models.append(
                {
                    "id": model_id,
                    "source": SOURCE_NAME,
                    "url": normalize_model_url(model_id),
                    "author": derive_author(model_id, raw.get("author")),
                    "created_at": created.isoformat(),
                    "pipeline_tag": raw.get("pipeline_tag") or "",
                    "library_name": raw.get("library_name") or "",
                    "downloads": raw.get("downloads") or 0,
                    "likes": raw.get("likes") or 0,
                    "tags": tags,
                    "content": build_content(raw),
                }
            )
        except Exception as exc:
            logger.warning("Skipping malformed model: %s", exc)
            continue
    return models


# ============================================================
# FETCH ALL — MULTI-SORT MERGE
# ============================================================

DEFAULT_SORTS = ["trendingScore", "createdAt", "downloads"]


def fetch_all_multi_sort(limit, sorts=None):
    """
    Fetch top N from each sort mode, merge, dedupe by id.
    Returns a list of unique models, newest first.
    """
    if sorts is None:
        sorts = DEFAULT_SORTS

    all_models = []
    seen_ids = set()

    for sort in sorts:
        print(f"  sort={sort}")
        try:
            raw = fetch_page(sort, limit=HF_MAX_PER_REQUEST)
        except Exception as exc:
            print(f"    fetch failed: {exc}")
            continue

        page_models = parse_models(raw)
        fresh = 0
        for model in page_models:
            if model["id"] in seen_ids:
                continue
            seen_ids.add(model["id"])
            all_models.append(model)
            fresh += 1

        print(f"    got={len(raw):>4} | new={fresh:>4} | total={len(all_models)}")
        time.sleep(REQUEST_DELAY)

        if len(all_models) >= limit:
            break

    return all_models


def fetch_all_incremental(cutoff_date):
    """
    Fetch newest models (sort=createdAt), stop early once we hit models
    older than cutoff_date.
    """
    try:
        raw = fetch_page("createdAt", limit=HF_MAX_PER_REQUEST)
    except Exception as exc:
        print(f"  fetch failed: {exc}")
        return []

    models = parse_models(raw)
    fresh = []

    for model in models:
        created = parse_date_string(model.get("created_at"))
        if created is None:
            continue
        if created >= cutoff_date:
            fresh.append(model)
        else:
            # results are newest-first; once we see an older one, stop
            break

    print(f"    got={len(models)} | fresh since {cutoff_date}={len(fresh)}")
    return fresh


# ============================================================
# AUDIT
# ============================================================

def audit():
    models = load_existing_models()

    print()
    print("=" * 60)
    print("HUGGING FACE CONTENT AUDIT")
    print("=" * 60)

    if not models:
        print("No models stored yet.")
        return

    dates = sorted(m["created_at"] for m in models if m.get("created_at"))
    tags_counter = {}
    lib_counter = {}
    pipeline_counter = {}

    for m in models:
        for t in m.get("tags") or []:
            tags_counter[t] = tags_counter.get(t, 0) + 1
        lib = m.get("library_name")
        if lib:
            lib_counter[lib] = lib_counter.get(lib, 0) + 1
        pipe = m.get("pipeline_tag")
        if pipe:
            pipeline_counter[pipe] = pipeline_counter.get(pipe, 0) + 1

    print("Models             :", len(models))
    print("Unique ids         :", len({m["id"] for m in models if m.get("id")}))
    if dates:
        print("Created range      :", dates[0], "->", dates[-1])

    print()
    print("Top libraries:")
    for lib, n in sorted(lib_counter.items(), key=lambda x: -x[1])[:10]:
        print(f"  {lib:22s} : {n}")

    print()
    print("Top pipeline tags:")
    for pipe, n in sorted(pipeline_counter.items(), key=lambda x: -x[1])[:10]:
        print(f"  {pipe:30s} : {n}")

    print()
    print("Top 20 tags:")
    for tag, n in sorted(tags_counter.items(), key=lambda x: -x[1])[:20]:
        print(f"  {tag:30s} : {n}")


# ============================================================
# RUN
# ============================================================

def run(args):
    print()
    print("=" * 60)
    print("HUGGING FACE SCRAPER")
    print("=" * 60)

    state = load_state()

    existing = load_existing_models()
    print(f"Existing models : {len(existing)}")

    if args.incremental:
        last = state.get("last_created_at")
        if not last:
            print("MODE: INCREMENTAL -> no prior state, falling back to multi-sort")
            new_models = fetch_all_multi_sort(args.limit, sorts=args.sorts)
        else:
            cutoff = parse_date_string(last)
            print(f"MODE: INCREMENTAL (since {cutoff})")
            new_models = fetch_all_incremental(cutoff)
    else:
        print(f"MODE: MULTI-SORT ({args.sorts})")
        new_models = fetch_all_multi_sort(args.limit, sorts=args.sorts)

    print()
    print(f"Fetched this run: {len(new_models)}")

    merged = merge_models(existing, new_models)
    save_json(OUTPUT_FILE, merged)

    if new_models:
        newest = max(m["created_at"] for m in new_models)
        state["last_created_at"] = newest
        save_state(state)

    print()
    print("=" * 60)
    print("RUN COMPLETE")
    print("=" * 60)
    print("New this run   :", len(new_models))
    print("Total stored   :", len(merged))
    print("Last created_at:", state.get("last_created_at"))
    print()
    print("Saved:", OUTPUT_FILE)


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Hugging Face models scraper")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help=f"total unique models target (default {DEFAULT_LIMIT})")
    parser.add_argument("--sorts", nargs="+", default=DEFAULT_SORTS,
                        help=f"sort modes to combine (default {DEFAULT_SORTS})")
    parser.add_argument("--incremental", action="store_true",
                        help="only fetch models created since last stored created_at")
    parser.add_argument("--audit", action="store_true",
                        help="print a quality report and exit")
    args = parser.parse_args()

    if args.audit:
        audit()
        return

    run(args)


if __name__ == "__main__":
    main()