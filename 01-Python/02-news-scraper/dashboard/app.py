"""
Indian AI Career & Startup Intelligence — Dashboard

Pages:
  Overview    — high-level stats + top skills/locations/companies
  Skills      — research-view skill distribution
  Companies   — top companies
  Locations   — cities
  News        — latest AI news
  Jobs        — ⭐ job market intelligence from Adzuna enriched data

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
    """Load Adzuna enriched jobs."""
    data = load_json("adzuna_enriched.json")
    if not isinstance(data, list) or not data:
        return pd.DataFrame()

    rows = []
    for j in data:
        if j.get("_enrichment_error"):
            continue
        rows.append({
            "title": j.get("title", ""),
            "company": j.get("company", ""),
            "location": j.get("location", ""),
            "url": j.get("url", ""),
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
# PAGE: JOBS  ⭐ NEW
# ============================================================

def page_jobs():
    st.title("💼 Job Market Intelligence")
    st.caption("Real India AI job data from Adzuna — skills, salaries, experience levels")

    df = jobs_df()
    if df.empty:
        st.warning("No enriched jobs yet. Run `python src/adzuna_enricher.py` first.")
        return

    # Header row: refresh + last updated
    col1, col2, col3 = st.columns([1, 1, 3])
    with col1:
        if st.button("🔄 Refresh"):
            st.cache_data.clear()
            st.rerun()
    with col2:
        mtime = file_mtime("adzuna_enriched.json")
        if mtime:
            st.caption(f"Updated: {mtime}")
    with col3:
        st.caption(f"Source: **{len(df)}** real jobs from Adzuna India")

    st.divider()

    # --- Top 20 skills in demand ---
    st.subheader("🎯 Top 20 skills in demand")
    skill_counts = {}
    for skills in df["required_skills"]:
        for s in skills:
            skill_counts[s] = skill_counts.get(s, 0) + 1
    sk_df = pd.DataFrame(
        [{"skill": k, "count": v} for k, v in skill_counts.items()]
    ).sort_values("count", ascending=False).head(20).reset_index(drop=True)

    if not sk_df.empty:
        fig = px.bar(
            sk_df, x="count", y="skill", orientation="h",
            color="count", color_continuous_scale="Viridis",
            text="count",
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(
            height=600, yaxis=dict(autorange="reversed"),
            coloraxis_showscale=False,
            margin=dict(l=0, r=40, t=10, b=10),
        )
        st.plotly_chart(fig, width='stretch')

    st.divider()

    # --- Skills by role + by experience ---
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Skills by role category")
        role_options = sorted([r for r in df["role_category"].unique() if r])
        selected_role = st.selectbox("Select role", ["— All —"] + role_options)

        if selected_role != "— All —":
            sub = df[df["role_category"] == selected_role]
            role_skills = {}
            for skills in sub["required_skills"]:
                for s in skills:
                    role_skills[s] = role_skills.get(s, 0) + 1
            role_df = pd.DataFrame(
                [{"skill": k, "count": v} for k, v in role_skills.items()]
            ).sort_values("count", ascending=False).head(15).reset_index(drop=True)

            if not role_df.empty:
                fig2 = px.bar(
                    role_df, x="count", y="skill", orientation="h",
                    color="count", color_continuous_scale="Blues",
                )
                fig2.update_layout(
                    height=500, yaxis=dict(autorange="reversed"),
                    coloraxis_showscale=False,
                    margin=dict(l=0, r=0, t=10, b=10),
                )
                st.plotly_chart(fig2, width='stretch')

    with col2:
        st.subheader("Skills by experience level")
        exp_options = sorted([e for e in df["experience_level"].unique() if e and e != "unknown"])
        selected_exp = st.selectbox("Select level", ["— All —"] + exp_options)

        if selected_exp != "— All —":
            sub = df[df["experience_level"] == selected_exp]
            exp_skills = {}
            for skills in sub["required_skills"]:
                for s in skills:
                    exp_skills[s] = exp_skills.get(s, 0) + 1
            exp_df = pd.DataFrame(
                [{"skill": k, "count": v} for k, v in exp_skills.items()]
            ).sort_values("count", ascending=False).head(15).reset_index(drop=True)

            if not exp_df.empty:
                fig3 = px.bar(
                    exp_df, x="count", y="skill", orientation="h",
                    color="count", color_continuous_scale="Greens",
                )
                fig3.update_layout(
                    height=500, yaxis=dict(autorange="reversed"),
                    coloraxis_showscale=False,
                    margin=dict(l=0, r=0, t=10, b=10),
                )
                st.plotly_chart(fig3, width='stretch')

    st.divider()

    # --- Experience level distribution ---
    st.subheader("Experience level distribution")
    exp_dist = df["experience_level"].value_counts().reset_index()
    exp_dist.columns = ["level", "count"]
    if not exp_dist.empty:
        fig4 = px.bar(
            exp_dist, x="level", y="count",
            color="level",
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig4.update_layout(
            showlegend=False, height=350,
            margin=dict(l=0, r=0, t=10, b=10),
        )
        st.plotly_chart(fig4, width='stretch')

    st.divider()

    # --- Job listings with filters ---
    st.subheader("🔍 Real job listings")

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        f_role = st.selectbox("Role", ["All"] + sorted(df["role_category"].unique().tolist()), key="jrole")
    with c2:
        # extract just the city (first token before comma)
        cities = sorted({(loc.split(",")[0].strip() if loc else "Unknown") for loc in df["location"].unique()})
        f_city = st.selectbox("City", ["All"] + cities, key="jcity")
    with c3:
        f_exp = st.selectbox("Experience", ["All"] + exp_options, key="jexp")
    with c4:
        f_skill = st.text_input("Skill contains", "", key="jskill")

    filtered = df.copy()
    if f_role != "All":
        filtered = filtered[filtered["role_category"] == f_role]
    if f_city != "All":
        filtered = filtered[filtered["location"].str.contains(f_city, case=False, na=False)]
    if f_exp != "All":
        filtered = filtered[filtered["experience_level"] == f_exp]
    if f_skill:
        filtered = filtered[filtered["required_skills"].apply(
            lambda skills: any(f_skill.lower() in s.lower() for s in (skills or []))
        )]

    st.caption(f"Showing **{len(filtered)}** jobs")

    for _, row in filtered.head(30).iterrows():
        with st.container(border=True):
            st.markdown(f"### {row['title']}")
            st.markdown(
                f"**{row['company']}** · {row['location']} · "
                f"{row['experience_level']} · "
                f"{row['salary_range_lpa'] or '—'} LPA · "
                f"{row['employment_type'] or '—'}"
            )

            if row["experience_min"] is not None or row["experience_max"] is not None:
                lo = row["experience_min"] if row["experience_min"] is not None else "?"
                hi = row["experience_max"] if row["experience_max"] is not None else "?"
                st.caption(f"Experience: {lo}-{hi} years")

            if row["required_skills"]:
                st.markdown("**Required skills:** " + ", ".join(row["required_skills"]))

            if row["nice_to_have_skills"]:
                st.markdown("**Nice to have:** " + ", ".join(row["nice_to_have_skills"]))

            if row["responsibilities_summary"]:
                st.caption(row["responsibilities_summary"])

            if row["url"]:
                st.markdown(f"[Apply →]({row['url']})")


# ============================================================
# PAGE: SKILLS (research view — unchanged)
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