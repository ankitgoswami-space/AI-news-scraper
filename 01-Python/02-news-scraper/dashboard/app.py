"""
Indian AI Career & Startup Intelligence — Dashboard

Streamlit dashboard over the project's V1-V3 outputs:
  - Skills intelligence (57 skills × 13 sources)
  - Company signals (50+ companies)
  - Location signals (18 cities)
  - Latest news feed (AIM, ET, Mint, Inc42, YourStory, TechCrunch)

Run:
    streamlit run dashboard/app.py
"""

import json
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
# DATA LOADERS (cached)
# ============================================================

@st.cache_data
def load_json(filename):
    path = DATA_DIR / filename
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


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
    """Aggregate news from all news sources."""
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
def stats():
    """Overview stats."""
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
    }


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("🇮🇳 Indian AI Career")
st.sidebar.caption("Intelligence Platform")
st.sidebar.divider()

page = st.sidebar.radio(
    "Navigate",
    ["Overview", "Skills", "Companies", "Locations", "News"],
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
    st.caption("What's happening in India's AI ecosystem — from 13 sources, 16,000+ records")

    s = stats()
    sk = skills_df()
    co = companies_df()
    lo = locations_df()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Sources", s["sources"])
    c2.metric("Records", f"{s['records']:,}")
    c3.metric("Skills tracked", len(sk))
    c4.metric("Companies", len(co))

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Top 10 skills")
        top10 = sk.head(10)
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
# PAGE: SKILLS
# ============================================================

def page_skills():
    st.title("🎯 Skills Intelligence")
    st.caption(f"57 skills tracked across 13 sources")

    df = skills_df()
    if df.empty:
        st.warning("No skills data. Run `python src/skills_extractor.py` first.")
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

    sources = row["sources"]
    src_df = pd.DataFrame(
        [{"source": k, "count": v} for k, v in sources.items()]
    ).sort_values("count", ascending=False)

    fig2 = px.pie(
        src_df, values="count", names="source",
        hole=0.4,
    )
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
elif page == "Skills":
    page_skills()
elif page == "Companies":
    page_companies()
elif page == "Locations":
    page_locations()
elif page == "News":
    page_news()
