"""
Master refresh script — runs all data pipelines in sequence.

Usage:
    python src/refresh_all.py                  # Full refresh
    python src/refresh_all.py --quick          # Skip slow enrichers
    python src/refresh_all.py --only scrapers  # Only scrapers
    python src/refresh_all.py --only v3        # Only V3 extractors
    python src/refresh_all.py --only v4        # Only V4 enrichers
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)


# ============================================================
# PIPELINE DEFINITIONS
# ============================================================

SCRAPERS = [
    ("TechCrunch",          "scraper_01_techcrunch.py",       []),
    ("AIM (weekly)",        "scraper_02_analytics_india.py",  []),
    ("Inc42",               "scraper_03_inc42.py",            []),
    ("YourStory",           "scraper_04_yourstory.py",        []),
    ("ET Tech",             "scraper_05_economic_times.py",   []),
    ("Mint",                "scraper_06_mint.py",             []),
    ("Hugging Face",        "scraper_11_huggingface.py",      ["--limit", "1000"]),
    ("arXiv",               "scraper_12_arxiv.py",            ["--incremental"]),
    ("Google Research",     "scraper_13_google_research.py",  []),
    ("Adzuna",              "scraper_adzuna.py",              []),
    ("HN Who's Hiring",     "scraper_hn_hiring.py",           []),
    ("RemoteOK",            "scraper_remoteok.py",            []),
    ("We Work Remotely",    "scraper_wwr.py",                 []),
]

V3_EXTRACTORS = [
    ("Skills",              "skills_extractor.py",             []),
    ("Companies/Locations", "company_location_extractor.py",   []),
]

V4_ENRICHERS = [
    ("Adzuna Enricher",     "adzuna_enricher.py",              ["--limit", "50"]),
    ("AIM Enricher",        "llm_enricher.py",                 ["--limit", "50"]),
    ("Blog Intel",          "blog_intel.py",                   []),
]


# ============================================================
# RUNNER
# ============================================================

def run_step(label, script, args, log_handle):
    script_path = SRC_DIR / script
    if not script_path.exists():
        msg = f"SKIP  {label:<22s} | {script} not found"
        print(msg)
        log_handle.write(msg + "\n")
        return "skipped"

    cmd = [sys.executable, str(script_path)] + args
    start = time.time()

    header = f"\n{'=' * 70}\nRUNNING: {label} | {script} {' '.join(args)}\n{'=' * 70}"
    print(header)
    log_handle.write(header + "\n")
    log_handle.flush()

    try:
        result = subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            timeout=7200,   # 2 hours max per script
        )
        elapsed = time.time() - start
        status = "OK" if result.returncode == 0 else "FAILED"
        msg = f"{status:<7s} {label:<22s} | {elapsed:>6.1f}s | exit={result.returncode}"
        print(msg)
        log_handle.write(msg + "\n")
        return status.lower()

    except subprocess.TimeoutExpired:
        msg = f"TIMEOUT {label:<22s} | >2h"
        print(msg)
        log_handle.write(msg + "\n")
        return "timeout"
    except Exception as exc:
        msg = f"ERROR   {label:<22s} | {exc}"
        print(msg)
        log_handle.write(msg + "\n")
        return "error"


def run_group(name, steps, log_handle):
    print(f"\n{'#' * 70}")
    print(f"# {name} ({len(steps)} steps)")
    print(f"{'#' * 70}")
    log_handle.write(f"\n{'#' * 70}\n# {name}\n{'#' * 70}\n")

    results = {}
    for label, script, args in steps:
        results[label] = run_step(label, script, args, log_handle)
    return results


def print_summary(all_results, log_handle, start_time):
    elapsed = time.time() - start_time
    ok = sum(1 for r in all_results.values() if r == "ok")
    failed = sum(1 for r in all_results.values() if r in ("failed", "error"))
    skipped = sum(1 for r in all_results.values() if r == "skipped")
    timeout = sum(1 for r in all_results.values() if r == "timeout")

    summary = f"""

{'=' * 70}
REFRESH SUMMARY
{'=' * 70}
Total time    : {elapsed / 60:.1f} minutes
Steps OK      : {ok}
Steps FAILED  : {failed}
Steps SKIPPED : {skipped}
Steps TIMEOUT : {timeout}
{'=' * 70}
"""
    print(summary)
    log_handle.write(summary)

    if failed or timeout:
        print("Failures:")
        log_handle.write("Failures:\n")
        for label, status in all_results.items():
            if status in ("failed", "error", "timeout"):
                line = f"  - {label}: {status}"
                print(line)
                log_handle.write(line + "\n")


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true",
                        help="Skip V4 enrichers (fast run)")
    parser.add_argument("--only", choices=["scrapers", "v3", "v4"],
                        help="Run only one group")
    args = parser.parse_args()

    today = datetime.now().strftime("%Y-%m-%d_%H-%M")
    log_path = LOG_DIR / f"refresh_{today}.log"

    print(f"\nStarting refresh at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Log file: {log_path}")

    start = time.time()
    all_results = {}

    with open(log_path, "w", encoding="utf-8") as log:
        log.write(f"Refresh started: {datetime.now().isoformat()}\n")

        if args.only in (None, "scrapers"):
            all_results.update(run_group("SCRAPERS (V1-V2)", SCRAPERS, log))

        if args.only in (None, "v3"):
            all_results.update(run_group("V3 EXTRACTORS", V3_EXTRACTORS, log))

        if args.only in (None, "v4") and not args.quick:
            all_results.update(run_group("V4 ENRICHERS", V4_ENRICHERS, log))

        print_summary(all_results, log, start)

    print(f"Log saved: {log_path}")


if __name__ == "__main__":
    main()