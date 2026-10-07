"""
Company and location extractor — V3 step 2 & 3.

Scans all 13 sources for:
  - Company mentions (Indian AI startups, IT services, global AI labs, chips, cloud)
  - Location mentions (Indian AI hubs + global + remote)

Companies and locations come from both:
  - Explicit `company` / `location` fields in job sources
  - Text scanning across all sources' title + content

Outputs:
  data/career_companies.json
  data/career_locations.json

Usage:
    python company_location_extractor.py
"""

import json
import re
from collections import defaultdict
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent.parent / "data"

SOURCES = {
    "analytics_india.json":   "AIM",
    "techcrunch.json":        "TechCrunch",
    "inc42.json":             "Inc42",
    "yourstory.json":         "YourStory",
    "economic_times.json":    "ET Tech",
    "mint.json":              "Mint",
    "arxiv.json":             "arXiv",
    "huggingface.json":       "Hugging Face",
    "google_research.json":   "Google Research",
    "adzuna.json":            "Adzuna India",
    "hn_hiring.json":         "HN Who's Hiring",
    "remoteok.json":          "RemoteOK",
    "wwr.json":               "We Work Remotely",
}

COMPANIES_FILE = DATA_DIR / "career_companies.json"
LOCATIONS_FILE = DATA_DIR / "career_locations.json"


# ============================================================
# COMPANY CATALOG
# ============================================================
# Curated to cover the Indian AI ecosystem:
# global AI labs, Indian AI startups, Indian IT services, chips, cloud.

COMPANIES = {
    # --- Global AI labs ---
    "OpenAI":            [r"\bopenai\b"],
    "Anthropic":         [r"\banthropic\b", r"\bclaude\b"],
    "Google":            [r"\bgoogle\b", r"\bdeepmind\b", r"\bgemini\b"],
    "Microsoft":         [r"\bmicrosoft\b"],
    "Meta":              [r"\bmeta\s+(?:ai|platforms|quest)\b", r"\bmeta'?s\b", r"\bllama\b", r"\bfacebook\b", r"\binstagram\b", r"\bwhatsapp\b"],
    "Mistral AI":        [r"\bmistral\b"],
    "NVIDIA":            [r"\bnvidia\b"],

    # --- Cloud / enterprise ---
    "Amazon / AWS":      [r"\bamazon\b", r"\baws\b"],
    "Oracle":            [r"\boracle\b"],
    "Salesforce":        [r"\bsalesforce\b"],
    "IBM":               [r"\bibm\b"],
    "Snowflake":         [r"\bsnowflake\b"],
    "Databricks":        [r"\bdatabricks\b"],
    "Adobe":             [r"\badobe\b"],
    "SAP":               [r"\bsap\b"],
    "Apple":             [r"\bapple\b"],

    # --- Chips / hardware ---
    "AMD":               [r"\bamd\b"],
    "Intel":             [r"\bintel\b"],
    "Qualcomm":          [r"\bqualcomm\b"],
    "TSMC":              [r"\btsmc\b"],
    "Broadcom":          [r"\bbroadcom\b"],

    # --- Indian AI startups ---
    "Sarvam AI":         [r"\bsarvam\b"],
    "Krutrim":           [r"\bkrutrim\b"],
    "BharatGPT":         [r"\bbharatgpt\b"],
    "Observe.AI":        [r"\bobserve\.?ai\b"],
    "Haptik":            [r"\bhaptik\b"],
    "Fractal":           [r"\bfractal\b"],
    "QpiAI":             [r"\bqpiai\b"],
    "Neysa":             [r"\bneysa\b"],

    # --- Indian IT services ---
    "TCS":               [r"\btcs\b", r"tata consultancy"],
    "Infosys":           [r"\binfosys\b"],
    "Wipro":             [r"\bwipro\b"],
    "HCLTech":           [r"\bhcltech\b", r"\bhcl tech\b", r"hcl technologies"],
    "Tech Mahindra":     [r"tech mahindra"],
    "Cognizant":         [r"\bcognizant\b"],
    "Accenture":         [r"\baccenture\b"],
    "Capgemini":         [r"\bcapgemini\b"],
    "LTIMindtree":       [r"\bltimindtree\b", r"\blt mindtree\b"],
}


# ============================================================
# LOCATION CATALOG
# ============================================================

LOCATIONS = {
    "Bengaluru":       [r"bengaluru", r"bangalore"],
    "Hyderabad":       [r"hyderabad"],
    "Gurgaon":         [r"gurgaon", r"gurugram"],
    "Noida":           [r"\bnoida\b"],
    "Mumbai":          [r"mumbai", r"bombay"],
    "Pune":            [r"\bpune\b"],
    "Chennai":         [r"chennai", r"madras"],
    "Delhi NCR":       [r"\bdelhi\b", r"new delhi"],
    "Kolkata":         [r"kolkata", r"calcutta"],
    "Ahmedabad":       [r"ahmedabad"],
    "Jaipur":          [r"jaipur"],
    "Kochi":           [r"kochi", r"cochin"],
    "Trivandrum":      [r"trivandrum", r"thiruvananthapuram"],
    "Indore":          [r"indore"],
    "Coimbatore":      [r"coimbatore"],
    "Remote":          [r"\bremote\b"],
    "United States":   [r"\busa\b", r"united states"],
    "United Kingdom":  [r"united kingdom", r"\buk\b", r"\blondon\b"],
}


def build_regex(patterns):
    combined = "|".join(f"(?:{p})" for p in patterns)
    return re.compile(f"(?:{combined})", re.IGNORECASE)


COMPILED_COMPANIES = {k: build_regex(v) for k, v in COMPANIES.items()}
COMPILED_LOCATIONS = {k: build_regex(v) for k, v in LOCATIONS.items()}


# ============================================================
# HELPERS
# ============================================================

def text_of_record(record):
    """Combine all searchable fields into one text blob."""
    parts = [
        record.get("title") or "",
        record.get("content") or "",
        record.get("location") or "",
        record.get("company") or "",
    ]
    return "\n".join(p for p in parts if p)


def scan(text, compiled):
    hits = {}
    for name, rx in compiled.items():
        n = len(rx.findall(text))
        if n:
            hits[name] = n
    return hits


# ============================================================
# MAIN
# ============================================================

def main():
    company_tally = defaultdict(lambda: defaultdict(int))
    company_totals = defaultdict(int)
    location_tally = defaultdict(lambda: defaultdict(int))
    location_totals = defaultdict(int)

    for filename, label in SOURCES.items():
        path = DATA_DIR / filename
        if not path.exists():
            print(f"  skip (missing): {filename}")
            continue

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            continue

        print(f"  scanning {label:<18s} ({len(data)} records)")

        for record in data:
            text = text_of_record(record)

            for name, n in scan(text, COMPILED_COMPANIES).items():
                company_tally[name][label] += n
                company_totals[name] += n

            for name, n in scan(text, COMPILED_LOCATIONS).items():
                location_tally[name][label] += n
                location_totals[name] += n

    companies_out = {
        "generated_from": "company_location_extractor.py",
        "companies": {
            name: {
                "total": company_totals[name],
                "sources": dict(sorted(company_tally[name].items(), key=lambda x: -x[1])),
            }
            for name in sorted(company_totals, key=lambda n: -company_totals[n])
        },
    }
    with open(COMPANIES_FILE, "w", encoding="utf-8") as f:
        json.dump(companies_out, f, ensure_ascii=False, indent=2)

    locations_out = {
        "generated_from": "company_location_extractor.py",
        "locations": {
            name: {
                "total": location_totals[name],
                "sources": dict(sorted(location_tally[name].items(), key=lambda x: -x[1])),
            }
            for name in sorted(location_totals, key=lambda n: -location_totals[n])
        },
    }
    with open(LOCATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(locations_out, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 70)
    print("TOP 20 COMPANIES")
    print("=" * 70)
    print(f"{'COMPANY':<20s} {'TOTAL':>8s}   TOP SOURCES")
    print("-" * 70)
    for name in sorted(company_totals, key=lambda n: -company_totals[n])[:20]:
        top = sorted(company_tally[name].items(), key=lambda x: -x[1])[:3]
        src = "  ".join(f"{s}:{n}" for s, n in top)
        print(f"{name:<20s} {company_totals[name]:>8d}   {src}")

    print()
    print("=" * 70)
    print("TOP LOCATIONS")
    print("=" * 70)
    print(f"{'LOCATION':<20s} {'TOTAL':>8s}   TOP SOURCES")
    print("-" * 70)
    for name in sorted(location_totals, key=lambda n: -location_totals[n]):
        top = sorted(location_tally[name].items(), key=lambda x: -x[1])[:3]
        src = "  ".join(f"{s}:{n}" for s, n in top)
        print(f"{name:<20s} {location_totals[name]:>8d}   {src}")

    print()
    print("Saved:", COMPANIES_FILE)
    print("Saved:", LOCATIONS_FILE)


if __name__ == "__main__":
    main()