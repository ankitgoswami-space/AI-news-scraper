"""
Indian AI Career & Startup Intelligence — Dashboard

Pages:
  Overview    — high-level stats + top skills/locations/companies
  Jobs        — ⭐ job market intelligence + personal match scoring
  Skills      — research-view skill distribution
  Companies   — top companies
  Locations   — cities
  News        — latest AI news

Run:
    streamlit run dashboard/app.py
"""

import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st


# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

st.set_page_config(
    page_title="Indian AI Career Intelligence",
    page_icon="🇮🇳",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# DATA LOADERS
# ============================================================

@st.cache_data
def load_json(filename):
    path = DATA_DIR / filename
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


@st.cache_data
def file_mtime(filename):
    path = DATA_DIR / filename
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


@st.cache_data
def skills_df():
    data = load_json("career_skills.json")
    if not data:
        return pd.DataFrame()
    rows = []
    for skill, info in data["skills"].items():
        rows.append({
            "skill": skill,
            "total": info["total"],
            "top_source": next(iter(info["sources"]), ""),
            "sources": info["sources"],
        })
    return pd.DataFrame(rows).sort_values("total", ascending=False).reset_index(drop=True)


@st.cache_data
def companies_df():
    data = load_json("career_companies.json")
    if not data:
        return pd.DataFrame()
    rows = [{"company": k, "total": v["total"]} for k, v in data["companies"].items()]
    return pd.DataFrame(rows).sort_values("total", ascending=False).reset_index(drop=True)


@st.cache_data
def locations_df():
    data = load_json("career_locations.json")
    if not data:
        return pd.DataFrame()
    rows = [{"location": k, "total": v["total"]} for k, v in data["locations"].items()]
    return pd.DataFrame(rows).sort_values("total", ascending=False).reset_index(drop=True)


@st.cache_data
def news_df():
    files = {
        "AIM": "analytics_india.json",
        "TechCrunch": "techcrunch.json",
        "Inc42": "inc42.json",
        "YourStory": "yourstory.json",
        "ET Tech": "economic_times.json",
        "Mint": "mint.json",
    }
    rows = []
    for label, filename in files.items():
        data = load_json(filename)
        if not isinstance(data, list):
            continue
        for a in data:
            rows.append({
                "source": label,
                "title": a.get("title", ""),
                "url": a.get("url", ""),
                "date": a.get("published_date", ""),
                "content": (a.get("content", "") or "")[:300],
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("date", ascending=False).reset_index(drop=True)
    return df


@st.cache_data
def jobs_df():
    """
    Load Adzuna enriched jobs.

    - Skips failed records
    - Dedupes by normalized URL (keeps first occurrence = most recent enrich)
    - Preserves published_date for freshness filtering
    """
    data = load_json("adzuna_enriched.json")
    if not isinstance(data, list) or not data:
        return pd.DataFrame()

    seen_urls = set()
    rows = []
    for j in data:
        if j.get("_enrichment_error"):
            continue

        url = (j.get("url") or "").strip().rstrip("/")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        rows.append({
            "title": j.get("title", ""),
            "company": j.get("company", ""),
            "location": j.get("location", ""),
            "url": url,
            "published_date": j.get("published_date", ""),
            "role_category": j.get("role_category", "") or "Unknown",
            "experience_min": j.get("experience_min_years"),
            "experience_max": j.get("experience_max_years"),
            "experience_level": j.get("experience_level", "") or "unknown",
            "employment_type": j.get("employment_type", "") or "",
            "remote_type": j.get("remote_type", "") or "",
            "salary_range_lpa": j.get("salary_range_lpa", "") or "",
            "required_skills": j.get("required_skills", []) or [],
            "nice_to_have_skills": j.get("nice_to_have_skills", []) or [],
            "responsibilities_summary": j.get("responsibilities_summary", "") or "",
        })
    return pd.DataFrame(rows)


@st.cache_data
def stats():
    def count(filename):
        data = load_json(filename)
        return len(data) if isinstance(data, list) else 0
    return {
        "sources": 13,
        "records": (
            count("analytics_india.json") + count("techcrunch.json")
            + count("inc42.json") + count("yourstory.json")
            + count("economic_times.json") + count("mint.json")
            + count("arxiv.json") + count("huggingface.json")
            + count("google_research.json") + count("adzuna.json")
            + count("hn_hiring.json") + count("remoteok.json")
            + count("wwr.json")
        ),
        "jobs": count("adzuna_enriched.json"),
    }


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("🇮🇳 Indian AI Career")
st.sidebar.caption("Intelligence Platform")
st.sidebar.divider()

page = st.sidebar.radio(
    "Navigate",
    ["Overview", "Jobs", "Skills", "Companies", "Locations", "News"],
)

st.sidebar.divider()
st.sidebar.caption("**Data sources**")
st.sidebar.caption(
    "6 news · 3 research · 4 jobs\n\n"
    "GitHub: [repo](https://github.com/ankitgoswami-space/AI-news-scraper)"
)


# ============================================================
# PAGE: OVERVIEW
# ============================================================

def page_overview():
    st.title("Indian AI Career & Startup Intelligence")
    st.caption("What's happening in India's AI ecosystem — from 13 sources")

    s = stats()
    sk = skills_df()
    co = companies_df()
    lo = locations_df()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sources", s["sources"])
    c2.metric("Records", f"{s['records']:,}")
    c3.metric("Skills tracked", len(sk))
    c4.metric("Jobs enriched", f"{s['jobs']:,}")

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Top 10 research skills")
        top10 = sk.head(10)
        if not top10.empty:
            fig = px.bar(
                top10, x="total", y="skill", orientation="h",
                color="total", color_continuous_scale="Blues",
            )
            fig.update_layout(
                showlegend=False, coloraxis_showscale=False,
                yaxis=dict(autorange="reversed"),
                height=400, margin=dict(l=0, r=0, t=10, b=10),
            )
            st.plotly_chart(fig, width='stretch')

    with col2:
        st.subheader("Top 10 locations")
        top10 = lo.head(10)
        if not top10.empty:
            fig = px.bar(
                top10, x="total", y="location", orientation="h",
                color="total", color_continuous_scale="Greens",
            )
            fig.update_layout(
                showlegend=False, coloraxis_showscale=False,
                yaxis=dict(autorange="reversed"),
                height=400, margin=dict(l=0, r=0, t=10, b=10),
            )
            st.plotly_chart(fig, width='stretch')

    st.divider()
    st.subheader("Top 10 companies")
    top10 = co.head(10)
    if not top10.empty:
        fig = px.bar(
            top10, x="company", y="total",
            color="total", color_continuous_scale="Oranges",
        )
        fig.update_layout(
            showlegend=False, coloraxis_showscale=False,
            height=350, margin=dict(l=0, r=0, t=10, b=10),
        )
        st.plotly_chart(fig, width='stretch')


# ============================================================
# JOB MATCHING HELPERS
# ============================================================

def compute_match(user_skills, job_skills):
    """Return (match_pct, matched_skills, missing_skills)."""
    if not job_skills:
        return 0, [], []
    user_set = set(user_skills)
    job_set = set(job_skills)
    matched = sorted(user_set & job_set)
    missing = sorted(job_set - user_set)
    pct = round(len(matched) / len(job_set) * 100) if job_set else 0
    return pct, matched, missing


def _render_job_card(row, show_match=False):
    """Render a single job card with optional match indicators."""
    with st.container(border=True):
        # Title + match badge
        if show_match and "match_pct" in row and pd.notna(row.get("match_pct")):
            pct = int(row.get("match_pct", 0))
            st.markdown(f"### {row['title']}  ·  `{pct}% match`")
        else:
            st.markdown(f"### {row['title']}")

        st.markdown(
            f"**{row['company']}** · {row['location']} · "
            f"{row['experience_level']} · "
            f"{row['salary_range_lpa'] or '—'} LPA · "
            f"{row['employment_type'] or '—'}"
        )

        if row.get("published_date"):
            st.caption(f"📅 Posted: {row['published_date']}")

        if row["experience_min"] is not None or row["experience_max"] is not None:
            lo = row["experience_min"] if row["experience_min"] is not None else "?"
            hi = row["experience_max"] if row["experience_max"] is not None else "?"
            st.caption(f"Experience: {lo}-{hi} years")

        # Skills
        if show_match and "matched_skills" in row:
            matched = row.get("matched_skills") or []
            missing = row.get("missing_skills") or []
            if matched:
                st.markdown("**✓ You have:** " + ", ".join(matched))
            if missing:
                display = missing[:8]
                suffix = " ..." if len(missing) > 8 else ""
                st.markdown("**✗ You need:** " + ", ".join(display) + suffix)
        else:
            if row["required_skills"]:
                st.markdown("**Required skills:** " + ", ".join(row["required_skills"]))
            if row["nice_to_have_skills"]:
                st.markdown("**Nice to have:** " + ", ".join(row["nice_to_have_skills"]))

        if row["responsibilities_summary"]:
            st.caption(row["responsibilities_summary"])

        if row["url"]:
            st.markdown(f"[Apply →]({row['url']})")


# ============================================================
# PAGE: JOBS
# ============================================================

def page_jobs():
    st.title("💼 Job Market Intelligence")
    st.caption("Real India AI jobs — with personal match scoring")

    df = jobs_df()
    if df.empty:
        st.warning("No enriched jobs yet. Run `python src/adzuna_enricher.py` first.")
        return

    # Header row: refresh + last updated + total
    c1, c2, c3, c4 = st.columns([1, 1, 1, 3])
    with c1:
        if st.button("🔄 Refresh"):
            st.cache_data.clear()
            st.rerun()
    with c2:
        mtime = file_mtime("adzuna_enriched.json")
        if mtime:
            st.caption(f"Updated: {mtime}")
    with c3:
        st.caption(f"Total: **{len(df)}** unique jobs")

    # ---------- Your Profile ----------
    with st.expander("🎯 Your Profile — set skills to see match scores", expanded=False):
        all_skills = set()
        for sk in df["required_skills"]:
            for s in sk:
                all_skills.add(s)
        all_skills = sorted(all_skills)

        col1, col2 = st.columns([3, 1])
        with col1:
            user_skills = st.multiselect(
                "Your current skills",
                options=all_skills,
                default=[],
                key="user_skills",
                help="Select skills you already have. Jobs will be ranked by match.",
            )
        with col2:
            user_exp = st.number_input(
                "Years of exp",
                min_value=0, max_value=30, value=0, step=1,
                key="user_exp",
            )

    # ---------- Filters ----------
    st.divider()
    st.subheader("🔍 Filters")

    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        f_role = st.selectbox(
            "Role",
            ["All"] + sorted(df["role_category"].unique().tolist()),
            key="jrole",
        )
    with c2:
        cities = sorted({
            (loc.split(",")[0].strip() if loc else "Unknown")
            for loc in df["location"].unique()
        })
        f_city = st.selectbox("City", ["All"] + cities, key="jcity")
    with c3:
        exp_options = sorted([
            e for e in df["experience_level"].unique()
            if e and e != "unknown"
        ])
        f_exp = st.selectbox("Experience", ["All"] + exp_options, key="jexp")
    with c4:
        f_fresh = st.selectbox(
            "Posted",
            ["All time", "Last 7 days", "Last 14 days", "Last 30 days"],
            key="jfresh",
        )
    with c5:
        if user_skills:
            f_sort = st.selectbox(
                "Sort",
                ["Best match", "Newest"],
                key="jsort",
            )
        else:
            f_sort = "Newest"
            st.caption("Sort: Newest")
            st.caption("(set skills ↑ for match scoring)")

    # ---------- Apply Filters ----------
    filtered = df.copy()
    if f_role != "All":
        filtered = filtered[filtered["role_category"] == f_role]
    if f_city != "All":
        filtered = filtered[filtered["location"].str.contains(f_city, case=False, na=False)]
    if f_exp != "All":
        filtered = filtered[filtered["experience_level"] == f_exp]

    # Freshness filter
    if f_fresh != "All time":
        days_map = {"Last 7 days": 7, "Last 14 days": 14, "Last 30 days": 30}
        days = days_map[f_fresh]
        cutoff = (pd.Timestamp.now() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
        filtered = filtered[filtered["published_date"] >= cutoff]

    # Compute match scores if user has skills
    if user_skills and not filtered.empty:
        def _match(row):
            pct, matched, missing = compute_match(user_skills, row["required_skills"])
            return pd.Series([pct, matched, missing])

        filtered[["match_pct", "matched_skills", "missing_skills"]] = filtered.apply(_match, axis=1)

        if f_sort == "Best match":
            filtered = filtered.sort_values("match_pct", ascending=False)
        else:
            filtered = filtered.sort_values("published_date", ascending=False)
    else:
        filtered = filtered.sort_values("published_date", ascending=False)

    st.caption(f"**{len(filtered)}** jobs match your filters")

    # ---------- Jobs That Fit You ----------
    if user_skills and f_sort == "Best match" and not filtered.empty:
        st.divider()
        st.subheader("⭐ Best matches for you")
        top = filtered[filtered["match_pct"] >= 30].head(10)
        if top.empty:
            st.info("No strong matches yet. Add more skills or relax the filters above.")
        else:
            for _, row in top.iterrows():
                _render_job_card(row, show_match=True)

    # ---------- Unlock Skills ----------
    if user_skills:
        st.divider()
        st.subheader("🎓 Skills that unlock more jobs")
        st.caption("Learning these would open up the most new opportunities")

        skill_opportunities = {}
        for sk_list in df["required_skills"]:
            for s in sk_list:
                if s not in user_skills:
                    skill_opportunities[s] = skill_opportunities.get(s, 0) + 1

        top_missing = sorted(skill_opportunities.items(), key=lambda x: -x[1])[:12]
        if top_missing:
            unlock_df = pd.DataFrame(
                [{"skill": s, "jobs_unlocked": n} for s, n in top_missing]
            )
            fig = px.bar(
                unlock_df, x="jobs_unlocked", y="skill", orientation="h",
                color="jobs_unlocked", color_continuous_scale="Greens",
                text="jobs_unlocked",
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(
                height=450, yaxis=dict(autorange="reversed"),
                coloraxis_showscale=False,
                margin=dict(l=0, r=40, t=10, b=10),
            )
            st.plotly_chart(fig, width='stretch')

    # ---------- All Jobs (paginated) ----------
    st.divider()
    st.subheader("📋 All matching jobs")

    # Reset pagination when filters change
    filter_key = f"{f_role}|{f_city}|{f_exp}|{f_fresh}|{f_sort}|{len(user_skills)}"
    if st.session_state.get("_jobs_filter_key") != filter_key:
        st.session_state["_jobs_filter_key"] = filter_key
        st.session_state["jobs_show"] = 30

    if "jobs_show" not in st.session_state:
        st.session_state["jobs_show"] = 30

    show_n = min(st.session_state["jobs_show"], len(filtered))
    for _, row in filtered.head(show_n).iterrows():
        _render_job_card(row, show_match=bool(user_skills))

    if show_n < len(filtered):
        remaining = len(filtered) - show_n
        if st.button(f"⬇ Load {min(30, remaining)} more ({remaining} remaining)"):
            st.session_state["jobs_show"] += 30
            st.rerun()


# ============================================================
# PAGE: SKILLS (research view)
# ============================================================

def page_skills():
    st.title("🎯 Research Skills")
    st.caption("Skills tracked across news, research, and papers (V3 output)")

    df = skills_df()
    if df.empty:
        st.warning("No skills data.")
        return

    col1, col2 = st.columns([1, 3])
    with col1:
        top_n = st.slider("Show top N", 10, 57, 25, 5)
    with col2:
        search = st.text_input("Search skill", "")

    filtered = df.copy()
    if search:
        filtered = filtered[filtered["skill"].str.contains(search, case=False, na=False)]

    top = filtered.head(top_n)
    if not top.empty:
        fig = px.bar(
            top, x="total", y="skill", orientation="h",
            color="total", color_continuous_scale="Viridis",
            hover_data=["top_source"],
        )
        fig.update_layout(
            height=max(400, top_n * 22),
            yaxis=dict(autorange="reversed"),
            margin=dict(l=0, r=0, t=10, b=10),
            coloraxis_showscale=False,
        )
        st.plotly_chart(fig, width='stretch')

    st.divider()
    st.subheader("Skill detail")

    selected = st.selectbox("Select a skill", df["skill"].tolist())
    row = df[df["skill"] == selected].iloc[0]
    st.metric("Total mentions", f"{row['total']:,}")

    src_df = pd.DataFrame(
        [{"source": k, "count": v} for k, v in row["sources"].items()]
    ).sort_values("count", ascending=False)

    fig2 = px.pie(src_df, values="count", names="source", hole=0.4)
    fig2.update_layout(height=400, margin=dict(l=0, r=0, t=10, b=10))
    st.plotly_chart(fig2, width='stretch')
    st.dataframe(src_df, width='stretch', hide_index=True)


# ============================================================
# PAGE: COMPANIES
# ============================================================

def page_companies():
    st.title("🏢 Company Signals")
    st.caption("Companies mentioned across news, research, and jobs")

    df = companies_df()
    if df.empty:
        st.warning("No company data.")
        return

    top_n = st.slider("Show top N", 10, len(df), 20, 5)
    top = df.head(top_n)
    fig = px.bar(
        top, x="total", y="company", orientation="h",
        color="total", color_continuous_scale="Oranges",
    )
    fig.update_layout(
        height=max(400, top_n * 22),
        yaxis=dict(autorange="reversed"),
        margin=dict(l=0, r=0, t=10, b=10),
        coloraxis_showscale=False,
    )
    st.plotly_chart(fig, width='stretch')

    st.subheader("Full table")
    st.dataframe(df, width='stretch', hide_index=True)


# ============================================================
# PAGE: LOCATIONS
# ============================================================

def page_locations():
    st.title("📍 Location Signals")
    st.caption("Where AI opportunities are concentrated")

    df = locations_df()
    if df.empty:
        st.warning("No location data.")
        return

    india_cities = {
        "Bengaluru", "Hyderabad", "Gurgaon", "Noida", "Mumbai",
        "Pune", "Chennai", "Delhi NCR", "Kolkata", "Ahmedabad",
        "Jaipur", "Kochi", "Trivandrum", "Indore", "Coimbatore",
    }
    india_df = df[df["location"].isin(india_cities)].reset_index(drop=True)

    st.subheader("India cities")
    fig = px.bar(
        india_df, x="total", y="location", orientation="h",
        color="total", color_continuous_scale="Greens",
    )
    fig.update_layout(
        height=max(400, len(india_df) * 28),
        yaxis=dict(autorange="reversed"),
        margin=dict(l=0, r=0, t=10, b=10),
        coloraxis_showscale=False,
    )
    st.plotly_chart(fig, width='stretch')

    st.subheader("All locations (incl. global)")
    st.dataframe(df, width='stretch', hide_index=True)


# ============================================================
# PAGE: NEWS
# ============================================================

def page_news():
    st.title("📰 Latest AI News")
    st.caption("From AIM, TechCrunch, Inc42, YourStory, ET Tech, Mint")

    df = news_df()
    if df.empty:
        st.warning("No news data.")
        return

    col1, col2 = st.columns([1, 3])
    with col1:
        sources = ["All"] + sorted(df["source"].unique().tolist())
        pick = st.selectbox("Source", sources)
    with col2:
        search = st.text_input("Search headlines", "")

    filtered = df.copy()
    if pick != "All":
        filtered = filtered[filtered["source"] == pick]
    if search:
        filtered = filtered[filtered["title"].str.contains(search, case=False, na=False)]

    st.caption(f"{len(filtered)} articles")

    for _, row in filtered.head(30).iterrows():
        with st.container(border=True):
            st.markdown(f"**{row['title']}**")
            st.caption(f"🔖 {row['source']} · {row['date']}")
            st.write(row["content"])
            st.markdown(f"[Read more →]({row['url']})")


# ============================================================
# ROUTER
# ============================================================

if page == "Overview":
    page_overview()
elif page == "Jobs":
    page_jobs()
elif page == "Skills":
    page_skills()
elif page == "Companies":
    page_companies()
elif page == "Locations":
    page_locations()
elif page == "News":
    page_news()