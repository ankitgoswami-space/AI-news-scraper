# Project 3 — Indian AI Career & Startup News Monitor

## Project Overview

A Python web-scraping project to collect and organize information relevant to India's AI ecosystem and AI career market.

### Personal problem

Information about Indian AI startups, AI jobs, skill requirements, opportunities, developments, and research is scattered across many websites.

The goal is to build a small monitor that collects this information automatically instead of manually checking multiple sources.

## Scope

### Locations
- Bengaluru
- Hyderabad
- Gurgaon / Gurugram
- Noida
- India-wide developments when relevant

### Information categories

**AI Startup Developments**
- New AI startups
- Funding
- Product launches
- Partnerships
- Acquisitions
- Major expansion/company developments

**Jobs & Opportunities**
- AI/ML Engineer
- GenAI Engineer
- LLM Engineer
- AI Research
- AI Trainer / AI Evaluation
- Data/ML roles
- Other emerging AI roles

**Skill Requirements**
Track skills actually mentioned by sources/job descriptions, such as:
- Python
- LLMs
- RAG
- AI Agents
- APIs
- Vector databases
- LangChain / LlamaIndex
- Cloud
- Docker
- ML/DL
- Data skills

**Research & Findings**
- New AI research
- Research findings
- New models
- Benchmarks
- Important technical developments
- India-related AI research

## Technical Goal

The first version is deliberately a **web-scraping project**, not an LLM project.

```text
Web Pages
    ↓
Requests
    ↓
HTML
    ↓
BeautifulSoup
    ↓
Extract information
    ↓
Clean / normalize
    ↓
Categorize
    ↓
JSON / CSV
    ↓
CLI output
```

### Main technologies
- Python
- Requests
- BeautifulSoup
- JSON
- CSV
- HTML parsing
- Basic text cleaning
- Git / GitHub

## MVP

The first working version should:

1. Fetch a web page.
2. Parse its HTML with BeautifulSoup.
3. Extract article titles.
4. Extract article URLs.
5. Extract dates/metadata where available.
6. Extract a short description/snippet where possible.
7. Store structured data.
8. Avoid obvious duplicates.
9. Display collected information in the CLI.
10. Be pushed to GitHub.

Example:

```text
INDIAN AI NEWS MONITOR
======================

1. AI Startup Development
   Title: ...
   Source: ...
   URL: ...

2. AI Jobs / Skills
   Title: ...
   Source: ...
   URL: ...

3. Research / New Development
   Title: ...
   Source: ...
   URL: ...
```

## Future Versions

### V2 — Better Data Collection
- Multiple sources
- More robust extraction
- Date filtering
- Category filtering
- Location filtering
- Duplicate detection
- Better error handling

### V3 — Career Intelligence
- Extract job titles
- Extract skills
- Identify companies
- Identify locations
- Compare recurring skill requirements

### V4 — GenAI Layer
- LLM summaries
- Automatic skill extraction
- News classification
- Company/event extraction
- Daily AI career briefing

### V5 — RAG / AI Assistant

```text
News Sources
    ↓
Scraper
    ↓
Clean Documents
    ↓
Chunking
    ↓
Embeddings
    ↓
Vector Database
    ↓
RAG
    ↓
"Which AI skills are appearing most often
in Indian GenAI jobs?"
```

## Today's 1-Hour Target

We have approximately one hour, so today's goal is **not to finish the whole project**.

### 0–10 min — Setup
- Create project folder
- Set up environment if needed
- Install `requests` and `beautifulsoup4`
- Create initial files

### 10–25 min — First scraper
Build:

```text
fetch page
    ↓
parse HTML
    ↓
find article elements
    ↓
extract title + URL
```

### 25–40 min — Structured output
Add:
- source
- title
- URL
- date if available
- category
- basic duplicate protection

Save to:

```text
data/news.json
```

### 40–50 min — Test
- Run the scraper
- Inspect output
- Handle at least one realistic failure case

### 50–60 min — GitHub
- Review files
- Update README
- `git add`
- `git commit`
- `git push`

## Proposed Folder Structure

```text
indian-ai-news-monitor/
│
├── data/
│   └── news.json
│
├── src/
│   └── scraper.py
│
├── .gitignore
├── README.md
├── requirements.txt
└── PROJECT_OVERVIEW.md
```

This structure can change if implementation gives us a good reason.

## Definition of Done — Today

- [ ] BeautifulSoup installed and working
- [ ] Requests can fetch a page
- [ ] BeautifulSoup parses HTML
- [ ] At least one real source is scraped
- [ ] Article title + URL extracted
- [ ] Data stored in JSON
- [ ] Script runs successfully
- [ ] Code is understandable
- [ ] Git commit created
- [ ] Project pushed to GitHub

**Important:** The project is not considered finished today. Today is the MVP foundation.

## Learning Outcomes

- HTTP requests
- HTML structure
- Web scraping
- BeautifulSoup selectors
- Extracting attributes
- Text cleaning
- Structured data
- JSON persistence
- Basic error handling
- Project organization
- Git workflow

## Long-Term Personal Goal

Eventually the project should help answer:

- What AI developments are happening in India's major tech hubs?
- What kinds of AI roles are appearing?
- Which skills are repeatedly mentioned?
- Which Indian AI startups are developing or hiring?
- What new AI research/developments are relevant?
- How are skill requirements changing over time?

### Core principle

> **Collect evidence first. Analyze later.**

The scraper should record what sources actually publish rather than inventing conclusions about the AI ecosystem or job market.
