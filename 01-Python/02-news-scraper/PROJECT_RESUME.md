# Indian AI Career & Startup Intelligence Platform

**A personal job-hunting tool + portfolio project**
Built to solve a real problem: finding AI/GenAI jobs in India across 13 scattered sources.

- **GitHub:** https://github.com/ankitgoswami-space/AI-news-scraper
- **Live Demo:** https://ankit-ai-career-intel.streamlit.app
- **Author:** Ankit Goswami

---

## 1. Tools & Technologies Used

### Languages
- **Python 3.14** — 100% of project

### Web Scraping
- **requests** — HTTP requests
- **BeautifulSoup4** — HTML/XML parsing
- **Playwright** — JS-rendered sites (AIM)
- **RSS/Atom feeds** — Inc42, YourStory, ET, Mint, WWR, Google Research

### APIs (5 sources)
- **Adzuna Jobs API** — India job listings
- **arXiv API** — research papers (Atom XML)
- **Hugging Face API** — models
- **HN Firebase API** — HackerNews Who's Hiring
- **RemoteOK API** — remote jobs

### LLM APIs
- **Google Gemini** (`gemini-flash-lite-latest`) — primary
- **Groq** (`openai/gpt-oss-120b`) — backup
- Structured JSON output + retry logic

### Dashboard
- **Streamlit** — 7-page interactive dashboard
- **Plotly** — interactive charts
- **Pandas** — data manipulation

### Document Parsing
- **pypdf** — resume text extraction
- **pymupdf (fitz)** — fallback PDF parser

### Automation
- **Windows Task Scheduler** — daily 2 AM runs
- **Batch scripting** (`run_daily.bat`) with UTF-8 encoding fix

### DevOps
- **Git + GitHub** — version control
- **Streamlit Cloud** — deployment
- **Environment management** — `.env`, `.gitignore`, secrets isolation

---

## 2. Concepts Applied

### Data Engineering
- Multi-source data pipeline — 13 sources, unified schema
- Idempotent scrapers — safe re-runs
- URL normalization for deduplication
- State management — resumable runs across sessions
- Checkpointing — save progress every N records
- Atomic file writes — `.tmp` + replace pattern

### Web Scraping
- Static scraping (`requests` + `BeautifulSoup`)
- Dynamic scraping (`Playwright` for JS-rendered AIM)
- Sitemap traversal — AIM AI-news sitemap
- Pagination — HF multi-sort merge (no offset support)
- Full-content fetch — RSS teaser → article body extraction

### API Engineering
- REST API integration — 5 different APIs
- Rate limit handling — 429/503 detection + exponential backoff
- Pagination strategies — offset, cursor, multi-sort
- Date-window chunking — arXiv weekly windows
- Authentication — API keys via `.env`

### LLM Engineering
- Structured extraction — prompt with JSON schema
- Closed-list constraints — prevent hallucination ("use only these 45 skills")
- Priority-based classification — ordered rules for category
- Few-shot prompt design
- Retry with backoff on transient errors
- Batch processing with checkpoint + resume

### Data Analysis
- Regex-based skill extraction — 57-skill catalog
- Company/location extraction — text scanning
- ATS scoring — 4-component weighted score
- Match scoring — user skills vs job requirements
- Reference data mining — blog → structured salary bands

### Software Engineering
- Separation of concerns — one scraper per source
- Shared utilities — `rss_common.py`, `ats_utils.py`
- Error classification — permanent vs temporary
- Logging — structured logs with timestamps
- CLI design — argparse with subcommands

### Deployment
- Cloud deployment — Streamlit Cloud
- Dependency management — `requirements.txt`
- Environment-specific fixes — UTF-8 on Windows
- Cache strategy — `@st.cache_data` for performance

### Personalization
- User profile — skills, experience, college
- Skill gap analysis — "learn X to unlock Y jobs"
- Referral workflow — LinkedIn search + templates
- Application tracking — JSON store with stats

---

## 3. What I Learned — Honest Self-Assessment

### Core Skills (Strong)
- ✅ Web scraping at production level — 13 sources, error handling
- ✅ API integration — multiple auth patterns, pagination
- ✅ LLM prompt engineering — structured extraction
- ✅ Data pipeline design — resilient, resumable
- ✅ Streamlit development — multi-page app
- ✅ Git discipline — meaningful commits, daily streak

### Concepts I Now Understand
- ✅ Rate limiting — how to handle 429/503 with backoff
- ✅ Idempotency — safe re-runs
- ✅ Deduplication — by normalized URL
- ✅ Retry with backoff — industry pattern
- ✅ Checkpointing — long-running job resumption
- ✅ Deployment — local vs production differences
- ✅ Secrets management — `.env`, `.gitignore`
- ✅ Dependency management — `requirements.txt`

### Gaps (For Interview Honesty)
- ⚠️ No tests — no unit/integration tests
- ⚠️ No CI/CD — manual deployment
- ⚠️ No containerization — no Docker
- ⚠️ Single user — no auth, no DB
- ⚠️ No vector DB / RAG yet — V5 pending

---

## 4. Resume-Ready Project Description

### Short Version (2 lines)

> **AI Career Intelligence Platform** — End-to-end data pipeline that scrapes 13 sources (news, research, jobs), enriches data with LLM, and serves a 7-page Streamlit dashboard with personal job matching, ATS optimization, and referral automation.

### Long Version (bullet points)

> **Indian AI Career & Startup Intelligence Platform** — [GitHub](link) · [Live Demo](link)
>
> - Built end-to-end data pipeline scraping **13 sources** (Indian news, arXiv, Hugging Face, Adzuna, HN) using Playwright, RSS, and 5 REST APIs — ~18K records
> - Designed **resilient scrapers** with checkpointing, retry-with-backoff, error classification (permanent vs temporary), and URL-based deduplication
> - Integrated **LLM enrichment** (Gemini + Groq) to extract structured fields (summary, companies, technologies, skills, category) from raw text, handling rate limits with exponential backoff
> - Developed a **7-page interactive dashboard** (Streamlit, Plotly) with personal match scoring, ATS resume checker, LinkedIn referral finder, and application tracker
> - Deployed on **Streamlit Cloud** with daily 2 AM automation via Windows Task Scheduler
> - **Tech:** Python, Playwright, BeautifulSoup, Streamlit, Plotly, Pandas, Gemini API, Groq API, REST APIs, Git

---

## 5. Is It Resume-Worthy?

### Honest Answer: **YES. It's a strong project.**

### Why It's Strong

| Criteria | This Project |
|---|---|
| Scope | End-to-end (scraping → LLM → dashboard → deployment) |
| Breadth | Web scraping + API + LLM + dashboard + automation |
| Uniqueness | Not a tutorial clone — original Indian AI ecosystem focus |
| Production polish | Error handling, retries, checkpointing, logs |
| Live deployment | Real URL, not just code on GitHub |
| Real problem | Personal job-hunting tool, not a toy project |
| Depth | 5+ months of iterative development, 40+ commits |
| Data scale | 18,000+ records across 13 sources |

### Where It Stands vs Typical Fresher Projects

| Project Type | Value |
|---|---|
| To-Do App | ❌ Skip — every fresher has one |
| Weather App | ❌ Skip |
| Titanic ML | ⚠️ Common |
| Basic Chatbot | ⚠️ Common |
| **This Project** | ✅ **Standout** |

### Why Recruiters Will Notice

1. **Live URL** — they can click and use it
2. **Multiple domains** — scraping + API + LLM + frontend
3. **Real problem** — "this person built a tool to solve their own problem"
4. **Production thinking** — retries, checkpointing, error handling
5. **Latest tech** — LLM integration, Streamlit Cloud, Gemini API
6. **Data engineering at scale** — 18K records, 13 sources

### What's Still Missing (For Even Stronger Profile)

- ❌ No blog post — write one, it adds narrative
- ❌ No RAG / V5 — would add "AI engineer" depth
- ❌ No tests — add some for "production" credibility
- ❌ Not on Docker — would add "DevOps" angle

---

## 6. Interview Talking Points

### Q: Tell me about a project you built recently?

> "I built a personal AI career intelligence platform to solve my own job-hunting problem. The idea: instead of checking 10 different websites, I wanted one tool that shows which AI jobs fit me, what skills I need, and how to reach out for referrals. I scraped 13 sources including Indian news sites, research papers, and job boards like Adzuna, then used Gemini to enrich each article with structured data. The dashboard is live at [URL]. Along the way I learned a lot about handling rate limits, designing idempotent pipelines, and dealing with the difference between local and deployed environments."

### Q: What was the hardest part?

> "Handling the AIM news site — it's JavaScript-rendered, so `requests` didn't work. I had to use Playwright and then figure out why some articles had extraction failures. Turns out my H1-selector was matching the wrong heading. Took me 4 days to debug, but taught me the value of writing diagnostics before writing fixes."

### Q: How did you handle rate limits?

> "Each API had different limits. For arXiv I used date-window chunking. For Gemini free tier (~1M tokens/day) I hit 429 errors mid-run. The fix was retry-with-exponential-backoff plus checkpointing every 25 records so a failed run could resume. I also added error classification — 404s are permanent (skip forever), but connection errors are temporary (retry next run)."

### Q: How do you ensure data quality?

> "Three layers: (1) URL normalization for deduplication, (2) minimum content threshold — reject if <300 chars, (3) audit scripts that report length distribution and date coverage. For LLM extractions I use closed-list constraints (only 45 pre-approved skills) to prevent hallucination."

---

## 7. Bottom Line

**This project is the strongest asset in my portfolio.**

- It's not a tutorial clone — it's an original solution to a real problem
- It touches 5 domains: scraping, API integration, LLM engineering, dashboard, automation
- It's deployed live, not just sitting in a GitHub repo
- It has production-grade design (retries, checkpointing, error handling)
- It demonstrates the ability to ship end-to-end, not just write isolated scripts

**If presented properly, this single project demonstrates enough depth to replace 3-4 typical portfolio projects.**

---

## 8. Next Steps (Improvement Plan)

### Priority 1 — Blog Post (High Impact)
- **Title:** "How I Built an AI Career Intelligence Platform from 13 Sources"
- **Platform:** LinkedIn + dev.to / Hashnode / Medium
- **Time:** 3-4 hours
- **Impact:** Recruiter sees narrative before GitHub

### Priority 2 — V5 RAG Assistant
- LangChain + ChromaDB + Gemini
- Chat interface over project data
- **Time:** 4-6 hours
- **Impact:** Adds "AI engineer" depth to resume

### Priority 3 — Basic Tests
- Pytest for scraper utilities
- Mock API responses
- **Time:** 2-3 hours
- **Impact:** "Production-ready" credibility

### Priority 4 — Docker
- Dockerfile + docker-compose
- **Time:** 2 hours
- **Impact:** DevOps angle

---

**End of project documentation.**