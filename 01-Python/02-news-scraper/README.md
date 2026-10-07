# Indian AI Career & Startup Intelligence Platform

An end-to-end data platform for the Indian AI/GenAI ecosystem. It starts as a
multi-source data collector and progressively becomes a career intelligence
system with LLM processing, RAG, and a dashboard.

The goal: turn scattered information (news, research, jobs, startup activity)
into structured intelligence that answers questions like:

- What's happening in India's AI ecosystem?
- Which AI/GenAI skills are in demand?
- Which cities and companies are hiring?
- Which research areas are emerging?
- What should I learn next?

---

## Current Status

**V1 and V2 complete. 9 of 9 sources shipped (~14,600 records).**

| Version | Scope | Status |
|---|---|---|
| V1 | Basic web scraper | ✅ Complete |
| V2 | Multi-source data collection | ✅ Complete |
| V3 | Career intelligence (skills, companies, locations) | ✅ Complete |
| V4 | LLM intelligence layer | ⏳ Planned |
| V5 | RAG career assistant | ⏳ Planned |
| V6 | Intelligence dashboard | ⏳ Planned |

### Top signals (V3 output)

**Top AI skills:**
| Skill | Mentions | Top source |
|---|---|---|
| LLM | 9,334 | arXiv |
| Transformers | 6,115 | Hugging Face |
| Agentic AI | 4,163 | arXiv / AIM |
| Fine-tuning | 3,417 | arXiv / HF |
| Quantization | 3,204 | Hugging Face |
| Python | 445 | Adzuna India |
| AWS | 423 | Adzuna India |
| SQL | 201 | arXiv / Adzuna |

**Top cities (India):** Bengaluru, Hyderabad, Mumbai, Chennai, Pune, Delhi NCR, Noida, Gurgaon

**Top companies:** Google, Anthropic, OpenAI, NVIDIA, Meta, Amazon/AWS, Microsoft, TCS, Infosys, Sarvam AI

### What's actually shipped

| Source | Type | Records | Method |
|---|---|---|---|
| TechCrunch (AI) | News | ~36 | requests + BeautifulSoup |
| Analytics India Magazine | News | 999 | Playwright (JS-rendered) |
| Inc42 | News | 24 | RSS |
| YourStory | News | 20 | RSS |
| Economic Times – Tech | News | 50 | RSS + full-content fetch |
| Mint – Technology | News | 35 | RSS + full-content fetch |
| arXiv (cs.AI, cs.CL, cs.LG) | Research | 10,621 | REST API (Atom XML) |
| Hugging Face | Models | 2,779 | REST API (multi-sort merge) |
| Google Research | Research | 100 | RSS + full-content fetch |

**Total: ~14,664 structured records, 0 missing dates, deduplicated by URL.**

---

## Dataset Schema

Each record follows a common shape, with source-specific extras where useful.

**News articles (AIM, TechCrunch):**

```json
{
  "title": "...",
  "source": "Analytics India Magazine",
  "url": "https://analyticsindiamag.com/ai-news/...",
  "published_date": "2026-08-24",
  "content": "clean article body"
}
```

**Research papers (arXiv):**

```json
{
  "title": "...",
  "source": "arXiv",
  "url": "https://arxiv.org/abs/2610.03717",
  "published_date": "2026-10-02",
  "content": "abstract",
  "authors": ["..."],
  "categories": ["cs.AI", "cs.CL"],
  "primary_category": "cs.AI"
}
```

---

## Project Structure

```text
02-news-scraper/
├── src/
│   ├── scraper_01_techcrunch.py           # V1 reference
│   ├── scraper_02_analytics_india.py      # Playwright scraper
│   ├── scraper_12_arxiv.py                # API scraper
│   ├── scraper_03..06_*.py                # Placeholders (Inc42, YourStory, ET, Mint)
│   
├── data/
│   ├── techcrunch.json
│   ├── analytics_india.json               # 999 articles
│   ├── analytics_india_state.json         # runtime state (for resume)
│   ├── arxiv.json                         # 10,621 papers
│   └── arxiv_state.json                   # incremental tracking
├── requirements.txt
└── README.md
```

---

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate           # Windows
pip install -r requirements.txt
playwright install chromium      # required for the AIM scraper
```

---

## Usage

### Analytics India Magazine (Playwright)

```bash
# One-time backfill: 1 Jan 2026 -> today
python src/scraper_02_analytics_india.py --force-initial --max-urls 0

# Weekly refresh: Monday -> today
python src/scraper_02_analytics_india.py

# Re-extract short articles and retry failures
python src/scraper_02_analytics_india.py --refetch-short --max-urls 0

# Quality report (no fetching)
python src/scraper_02_analytics_india.py --audit
```

### arXiv (API)

```bash
# One-time backfill: last 30 days
python src/scraper_12_arxiv.py --days 30

# Incremental (since last stored date)
python src/scraper_12_arxiv.py --incremental

# Custom window
python src/scraper_12_arxiv.py --days 7 --max-results 200

# Quality report
python src/scraper_12_arxiv.py --audit
```

---

## Design Decisions

**Per-source isolation.** Each source lives in its own file. Source-specific
quirks stay local, failures don't cascade, and each scraper can be tested and
replaced independently.

**Normalized URLs as identity.** Deduplication uses a normalized URL
(scheme + host + path, no query, no trailing slash, no version suffix). This
keeps re-runs idempotent.

**State files, not memory.** Each scraper keeps its own state file
(`*_state.json`) so runs are resumable. Kill the process mid-run, restart, and
it picks up where it left off.

**Checkpointing.** Long runs write to disk every N items. A crash never loses
more than one checkpoint's worth of work.

**Honest scope.** This is a solo learning project. If a source needs paid
proxies, CAPTCHA solving, or login walls (LinkedIn, Naukri, Instahyre), it's
skipped. 9 working sources beat 15 broken ones.

---

## Roadmap

### V2: 9-source universe ✅ COMPLETE

- [x] TechCrunch
- [x] Analytics India Magazine
- [x] Inc42
- [x] YourStory
- [x] Economic Times – Tech
- [x] Mint – Technology
- [x] arXiv
- [x] Hugging Face
- [x] Google Research

### Later versions

### V3: career intelligence ✅ COMPLETE

- [x] Skills extraction (57 skills, `data/career_skills.json`)
- [x] Company extraction (50+ companies, `data/career_companies.json`)
- [x] Location extraction (18 cities, `data/career_locations.json`)
- [x] Per-source breakdowns (included in all three outputs)

**Top signals:**

| Category | Leaders |
|---|---|
| Skills | LLM (9334), Transformers (6115), Agentic AI (4163), Fine-tuning (3417), Python (445) |
| Companies | Google (3564), Anthropic (2067), OpenAI (1671), NVIDIA (1136), Sarvam AI (246) |
| Cities | Bengaluru (1888), Remote (812), Hyderabad (609), Mumbai (375), Chennai (301) |

- **V4:** LLM-powered summarization, entity extraction, classification, and trend detection.
- **V4:** (next):** LLM-powered summarization, entity extraction, classification, and trend detection.
- **V5:** RAG-based career assistant grounded in the project's own data.
- **V6:** Streamlit dashboard — skill trends, city/company insights, and chat.

---

## Sources Removed from Scope

These were in the original plan but are impractical without infrastructure
this project doesn't have:

| Source | Reason |
|---|---|
| LinkedIn Jobs | Login wall + aggressive anti-bot |
| Naukri | CAPTCHA, IP bans |
| Instahyre | Same as Naukri |
| Wellfound | Login-gated |
| IndiaAI | Messy HTML, low yield |
| MeitY | Low AI-career signal density |

Job and skill signals come instead from news and research content.

---

## Status Honesty

- All 9 sources are implemented.
- V2 is complete.
- The dataset is real, dated, deduplicated, and clean — but it's news and research, not job listings.

---

Repo: [github.com/ankitgoswami-space/AI-news-scraper](https://github.com/ankitgoswami-space/AI-news-scraper)
