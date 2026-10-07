"""
Skills extractor — V3 step 1.

Scans all collected sources and counts mentions of a curated skill list.
Output: data/career_skills.json with per-skill totals and per-source breakdown.

Usage:
    python skills_extractor.py
    python skills_extractor.py --top 30
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Source file -> 
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
    "adzuna.json":            "Adzuna India",        # NEW
    "hn_hiring.json":         "HN Who's Hiring",     # NEW
    "remoteok.json":          "RemoteOK",            # NEW
    "wwr.json":               "We Work Remotely",    # NEW
}

OUTPUT_FILE = DATA_DIR / "career_skills.json"


# ============================================================
# SKILLS CATALOG
# ============================================================
# Each skill maps to a list of regex patterns.
# Word boundaries (\b) are applied around the whole alternation
# so short names don't match inside unrelated words.

SKILLS = {
    # --- Programming languages ---
    "Python":         [r"python"],
    "JavaScript":     [r"javascript", r"node\.?js"],
    "TypeScript":     [r"typescript"],
    "Java":           [r"java(?!script)"],
    "C++":            [r"c\+\+"],
    "Rust":           [r"rust"],
    "Go":             [r"\bgolang\b", r"\bgo language\b"],
    "SQL":            [r"sql"],

    # --- ML / DL frameworks ---
    "PyTorch":        [r"pytorch", r"\btorch\b"],
    "TensorFlow":     [r"tensorflow"],
    "Keras":          [r"keras"],
    "JAX":            [r"\bjax\b"],
    "scikit-learn":   [r"scikit[- ]?learn", r"sklearn"],
    "Hugging Face":   [r"hugging ?face"],
    "Transformers":   [r"\btransformers?\b"],
    "Diffusers":      [r"diffusers?"],
    "PEFT":           [r"\bpeft\b"],
    "LoRA":           [r"\blora\b"],
    "vLLM":           [r"\bvllm\b"],
    "Ollama":         [r"ollama"],

    # --- AI / GenAI concepts ---
    "LLM":            [r"\bllms?\b", r"large language models?"],
    "RAG":            [r"\brag\b", r"retrieval[- ]augmented generation"],
    "LangChain":      [r"langchain"],
    "LlamaIndex":     [r"llamaindex", r"llama[- ]index"],
    "Vector DB":      [r"vector (?:db|database|store|search)s?"],
    "Embeddings":     [r"embeddings?"],
    "Fine-tuning":    [r"fine[- ]?tun(?:e|ing|ed)", r"\bsft\b", r"\brlhf\b", r"\bdpo\b"],
    "Quantization":   [r"quantiz(?:e|ed|ation|ing)", r"\bgguf\b", r"\bqat\b"],
    "Prompt Engg":    [r"prompt engineer", r"prompting", r"prompt design"],
    "Agentic AI":     [r"agentic", r"\bai agents?\b", r"autonomous agents?", r"multi[- ]agent"],
    "Multimodal":     [r"multimodal", r"multi[- ]modal"],
    "Reasoning":      [r"reasoning models?", r"chain[- ]of[- ]thought", r"\bcot\b"],
    "Diffusion":      [r"diffusion models?", r"stable diffusion"],
    "CUDA":           [r"\bcuda\b"],
    "GPU":            [r"\bgpus?\b"],
    "NVIDIA":         [r"\bnvidia\b"],
    "Machine Learning": [r"machine learning", r"\bml\b(?!\s*ops)"],
    "Deep Learning":    [r"deep learning", r"\bdl\b"],
    "NLP":              [r"\bnlp\b", r"natural language processing"],
    "Computer Vision":  [r"computer vision", r"\bcv\b"],
    "Machine Learning": [r"machine learning", r"\bml engineer"],
    "Deep Learning":    [r"deep learning", r"\bdl\b"],
    "NLP":              [r"\bnlp\b", r"natural language processing"],
    "Computer Vision":  [r"computer vision", r"\bcv engineer"],

    # --- Cloud / infra ---
    "AWS":            [r"\baws\b", r"amazon web services"],
    "Azure":          [r"\bazure\b"],
    "GCP":            [r"\bgcp\b", r"google cloud"],
    "Docker":         [r"docker"],
    "Kubernetes":     [r"kubernetes", r"\bk8s\b"],
    "MLOps":          [r"\bmlops\b"],
    "Git":            [r"\bgit\b", r"github", r"gitlab"],

    # --- Data ---
    "Spark":          [r"\bspark\b", r"pyspark"],
    "Kafka":          [r"kafka"],
    "Airflow":        [r"airflow"],
    "Snowflake":      [r"snowflake"],
    "Databricks":     [r"databricks"],
    "PostgreSQL":     [r"postgres(?:ql)?"],
    "MongoDB":        [r"mongodb"],

    # --- Indian ecosystem / companies (context) ---
    "Sarvam AI":      [r"sarvam"],
    "Krutrim":        [r"krutrim"],
    "Ola Krutrim":    [r"ola krutrim"],
    "BharatGPT":      [r"bharatgpt"],
}


COMPILED = {
    skill: re.compile(
        r"\b(?:" + "|".join(f"(?:{p})" for p in patterns) + r")\b",
        re.IGNORECASE,
    )
    for skill, patterns in SKILLS.items()
}


# ============================================================
# EXTRACTION
# ============================================================

def text_of_record(record):
    """
    Combine title + content + (for HF) tags + (for arXiv) authors and categories
    into one searchable blob.
    """
    parts = [
        record.get("title") or "",
        record.get("content") or "",
    ]

    # Hugging Face
    tags = record.get("tags")
    if isinstance(tags, list):
        parts.append(" ".join(tags))
    if record.get("library_name"):
        parts.append(record["library_name"])
    if record.get("pipeline_tag"):
        parts.append(record["pipeline_tag"])

    # arXiv
    cats = record.get("categories")
    if isinstance(cats, list):
        parts.append(" ".join(cats))

    return "\n".join(p for p in parts if p)


def extract_from_record(record):
    text = text_of_record(record)
    hits = {}
    for skill, rx in COMPILED.items():
        n = len(rx.findall(text))
        if n:
            hits[skill] = n
    return hits


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Extract skill mentions from all sources")
    parser.add_argument("--top", type=int, default=30,
                        help="show top N skills in the summary (default 30)")
    args = parser.parse_args()

    # skill -> {source_label: count}
    tally = defaultdict(lambda: defaultdict(int))
    # skill -> total
    totals = defaultdict(int)
    # source_label -> records processed
    records_per_source = defaultdict(int)
    # source_label -> total chars scanned
    chars_per_source = defaultdict(int)

    for filename, label in SOURCES.items():
        path = DATA_DIR / filename
        if not path.exists():
            print(f"  skip (missing): {filename}")
            continue

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            print(f"  skip (not a list): {filename}")
            continue

        print(f"  scanning {label:<18s} ({len(data)} records)")

        for record in data:
            records_per_source[label] += 1
            text = text_of_record(record)
            chars_per_source[label] += len(text)

            hits = extract_from_record(record)
            for skill, n in hits.items():
                tally[skill][label] += n
                totals[skill] += n

    # Build output
    output = {
        "generated_from": "skills_extractor.py",
        "sources_processed": {
            label: {
                "records": records_per_source[label],
                "chars_scanned": chars_per_source[label],
            }
            for label in records_per_source
        },
        "skills": {},
    }

    for skill in sorted(totals, key=lambda s: -totals[s]):
        output["skills"][skill] = {
            "total": totals[skill],
            "sources": dict(sorted(tally[skill].items(), key=lambda x: -x[1])),
        }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Print summary
    print()
    print("=" * 70)
    print(f"TOP {args.top} SKILLS (out of {len(totals)})")
    print("=" * 70)
    print(f"{'SKILL':<18s} {'TOTAL':>8s}   TOP SOURCES")
    print("-" * 70)

    for skill in sorted(totals, key=lambda s: -totals[s])[:args.top]:
        top_sources = sorted(tally[skill].items(), key=lambda x: -x[1])[:3]
        src_str = "  ".join(f"{s}:{n}" for s, n in top_sources)
        print(f"{skill:<18s} {totals[skill]:>8d}   {src_str}")

    print()
    print("Sources processed:")
    for label, n in records_per_source.items():
        print(f"  {label:<18s} {n:>6d} records, {chars_per_source[label]:>10,d} chars")

    print()
    print("Saved:", OUTPUT_FILE)


if __name__ == "__main__":
    main()