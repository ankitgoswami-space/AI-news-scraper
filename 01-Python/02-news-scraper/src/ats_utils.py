"""
ATS utilities — resume parsing, skill extraction, keyword matching.
Used by dashboard/app.py for the ATS Optimizer feature.
"""

import re
from collections import Counter


# ============================================================
# SKILLS CATALOG
# ============================================================

SKILLS_CATALOG = {
    "Python":       [r"python"],
    "JavaScript":   [r"javascript", r"node\.?js"],
    "TypeScript":   [r"typescript"],
    "Java":         [r"java(?!script)"],
    "C++":          [r"c\+\+"],
    "Rust":         [r"rust"],
    "Go":           [r"\bgolang\b"],
    "SQL":          [r"\bsql\b"],
    "PyTorch":      [r"pytorch"],
    "TensorFlow":   [r"tensorflow"],
    "Keras":        [r"keras"],
    "JAX":          [r"\bjax\b"],
    "scikit-learn": [r"scikit[- ]?learn", r"sklearn"],
    "Hugging Face": [r"hugging ?face"],
    "Transformers": [r"transformers?"],
    "Diffusers":    [r"diffusers?"],
    "PEFT":         [r"\bpeft\b"],
    "LoRA":         [r"\blora\b"],
    "vLLM":         [r"\bvllm\b"],
    "Ollama":       [r"ollama"],
    "LLM":          [r"\bllms?\b", r"large language models?"],
    "RAG":          [r"\brag\b", r"retrieval[- ]augmented"],
    "LangChain":    [r"langchain"],
    "LlamaIndex":   [r"llamaindex", r"llama[- ]index"],
    "Vector DB":    [r"vector (?:db|database|store|search)s?"],
    "Embeddings":   [r"embeddings?"],
    "Fine-tuning":  [r"fine[- ]?tun(?:e|ing|ed)", r"\bsft\b", r"\brlhf\b", r"\bdpo\b"],
    "Quantization": [r"quantiz(?:e|ed|ation|ing)", r"\bgguf\b"],
    "Prompt Engg":  [r"prompt engineer", r"prompting"],
    "Agentic AI":   [r"agentic", r"\bai agents?\b", r"multi[- ]agent"],
    "Multimodal":   [r"multimodal", r"multi[- ]modal"],
    "Reasoning":    [r"reasoning models?", r"chain[- ]of[- ]thought"],
    "Diffusion":    [r"diffusion models?", r"stable diffusion"],
    "MoE":          [r"\bmoe\b", r"mixture[- ]of[- ]experts"],
    "AWS":          [r"\baws\b", r"amazon web services"],
    "Azure":        [r"\bazure\b"],
    "GCP":          [r"\bgcp\b", r"google cloud"],
    "Docker":       [r"docker"],
    "Kubernetes":   [r"kubernetes", r"\bk8s\b"],
    "MLOps":        [r"\bmlops\b"],
    "Git":          [r"\bgit\b", r"github", r"gitlab"],
    "Linux":        [r"\blinux\b"],
    "Spark":        [r"\bspark\b", r"pyspark"],
    "Kafka":        [r"kafka"],
    "Airflow":      [r"airflow"],
    "Snowflake":    [r"snowflake"],
    "Databricks":   [r"databricks"],
    "PostgreSQL":   [r"postgres(?:ql)?"],
    "MongoDB":      [r"mongodb"],
    "React":        [r"\breact\b"],
    "Node.js":      [r"node\.?js"],
    "FastAPI":      [r"fastapi"],
    "Django":       [r"django"],
    "Flask":        [r"flask"],
    "REST API":     [r"rest ?api"],
    "GraphQL":      [r"graphql"],
    "Computer Vision": [r"computer vision"],
    "NLP":          [r"\bnlp\b", r"natural language processing"],
    "Deep Learning": [r"deep learning"],
    "Machine Learning": [r"machine learning"],
    "Pandas":       [r"\bpandas\b"],
    "NumPy":        [r"\bnumpy\b"],
    "Data Analysis": [r"data analy(?:sis|tics)"],
    "Statistics":   [r"statistic"],
}

COMPILED_SKILLS = {
    skill: re.compile(
        r"\b(?:" + "|".join(f"(?:{p})" for p in patterns) + r")\b",
        re.IGNORECASE,
    )
    for skill, patterns in SKILLS_CATALOG.items()
}


# ============================================================
# RESUME PARSING
# ============================================================

def extract_pdf_text(file_bytes):
    """Extract text from a PDF using pypdf."""
    try:
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in reader.pages:
            text += (page.extract_text() or "") + "\n"
        return text
    except Exception as e:
        raise RuntimeError(f"PDF extraction failed: {e}")


def extract_skills_from_text(text):
    """Return dict: skill -> count."""
    hits = {}
    for skill, rx in COMPILED_SKILLS.items():
        n = len(rx.findall(text))
        if n:
            hits[skill] = n
    return hits


def detect_contact_info(text):
    """Return dict with email, phone, linkedin, github presence."""
    return {
        "email": bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)),
        "phone": bool(re.search(r"(?:\+?\d[\d\s\-\(\)]{8,}\d)", text)),
        "linkedin": bool(re.search(r"linkedin\.com/in/", text, re.IGNORECASE)),
        "github": bool(re.search(r"github\.com/", text, re.IGNORECASE)),
    }


def count_words(text):
    return len(re.findall(r"\b\w+\b", text))


def has_section(text, keywords):
    text_lower = text.lower()
    return any(k in text_lower for k in keywords)


# ============================================================
# ATS SCORING
# ============================================================

def compute_ats_report(resume_text, resume_skills, job):
    """
    Return ATS report comparing resume vs job.

    Score:
      - Skill match (70%) — how many of job's required_skills are in resume
      - Contact info (10%)
      - Resume length (10%)
      - Section headers (10%)
    """
    job_skills = set(job.get("required_skills") or [])
    nice_skills = set(job.get("nice_to_have_skills") or [])
    resume_skill_set = set(resume_skills)

    matched_required = sorted(resume_skill_set & job_skills)
    missing_required = sorted(job_skills - resume_skill_set)
    matched_nice = sorted(resume_skill_set & nice_skills)

    # Skill score — require minimum skills for reliable scoring
    MIN_SKILLS_FOR_ATS = 3
    if not job_skills or len(job_skills) < MIN_SKILLS_FOR_ATS:
        # Not enough data — return low confidence score
        return {
            "score": 0,
            "skill_pct": 0,
            "contact_pct": 0,
            "length_pct": 0,
            "section_pct": 0,
            "matched_required": [],
            "missing_required": [],
            "matched_nice": [],
            "job_skills": sorted(job_skills),
            "job_nice_skills": sorted(nice_skills),
            "word_count": 0,
            "contacts": {},
            "insufficient_data": True,
        }

    skill_pct = len(matched_required) / len(job_skills) * 100

    # Contact score
    contacts = detect_contact_info(resume_text)
    contact_pct = sum(contacts.values()) / 4 * 100

    # Length score
    words = count_words(resume_text)
    if 250 <= words <= 900:
        length_pct = 100
    elif words < 250:
        length_pct = max(0, words / 250 * 100)
    else:
        length_pct = max(40, 100 - (words - 900) / 20)

    # Section score
    sections = [
        has_section(resume_text, ["skill", "technologies", "tech stack"]),
        has_section(resume_text, ["experience", "work history", "employment"]),
        has_section(resume_text, ["education", "degree", "university", "college"]),
        has_section(resume_text, ["project", "portfolio"]),
    ]
    section_pct = sum(sections) / len(sections) * 100

    total = (
        skill_pct * 0.70
        + contact_pct * 0.10
        + length_pct * 0.10
        + section_pct * 0.10
    )

    return {
        "score": round(total),
        "skill_pct": round(skill_pct),
        "contact_pct": round(contact_pct),
        "length_pct": round(length_pct),
        "section_pct": round(section_pct),
        "matched_required": matched_required,
        "missing_required": missing_required,
        "matched_nice": matched_nice,
        "job_skills": sorted(job_skills),
        "job_nice_skills": sorted(nice_skills),
        "word_count": words,
        "contacts": contacts,
    }