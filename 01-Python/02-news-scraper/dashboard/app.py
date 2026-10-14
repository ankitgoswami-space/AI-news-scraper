"""
Indian AI Career & Startup Intelligence — Dashboard

Pages:
  Overview    — high-level stats + top skills/locations/companies
  Jobs        — ⭐ job market intelligence + personal match scoring + referral + applied tracker
  ATS Checker — resume vs job ATS matching
  Skills      — research-view skill distribution
  Companies   — top companies
  Locations   — cities
  News        — latest AI news

Run:
    streamlit run dashboard/app.py
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# Allow importing from src/
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from ats_utils import (
    extract_pdf_text,
    extract_skills_from_text,
    detect_contact_info,
    count_words,
    compute_ats_report,
)
from referral_utils import (
    build_linkedin_searches,
    format_template,
    TEMPLATE_PEER,
    TEMPLATE_HR,
    TEMPLATE_ALUMNI,
)
from applications_utils import (
    load_applications,
    add_application,
    remove_application,
    stats as app_stats,
)
try:
    from rag_query import query as rag_query_fn
    RAG_AVAILABLE = True
except Exception as _rag_err:
    RAG_AVAILABLE = False
    _rag_err_msg = str(_rag_err)

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
    ["Overview", "Jobs", "Ask AI", "ATS Checker", "Skills", "Companies", "Locations", "News"],
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

MIN_SKILLS_FOR_MATCH = 3


def compute_match(user_skills, job_skills):
    if not job_skills or len(job_skills) < MIN_SKILLS_FOR_MATCH:
        return None, [], []
    user_set = set(user_skills)
    job_set = set(job_skills)
    matched = sorted(user_set & job_set)
    missing = sorted(job_set - user_set)
    pct = round(len(matched) / len(job_set) * 100)
    return pct, matched, missing


def _render_referral_section(job):
    """Render LinkedIn searches + outreach templates for a job."""
    user_profile = st.session_state.get("_user_profile", {})

    with st.expander("🔗 Find Referral (LinkedIn + templates)"):
        st.markdown("**1. Find people on LinkedIn**")
        st.caption("Click to open LinkedIn search in new tab. Then pick a profile to DM.")

        searches = build_linkedin_searches(
            job, user_college=user_profile.get("college", "")
        )
        for label, url in searches:
            st.markdown(f"- [{label}]({url})")

        st.divider()
        st.markdown("**2. Outreach templates**")
        st.caption(
            "Fill `[Name]` with the person's real name before sending. "
            "Keep it short — long DMs get ignored."
        )

        templates = [
            ("📧 Peer / Same role", TEMPLATE_PEER),
            ("📧 Recruiter / HR",   TEMPLATE_HR),
        ]
        if user_profile.get("college"):
            templates.append(("📧 Alumni", TEMPLATE_ALUMNI))

        for label, tmpl in templates:
            filled = format_template(tmpl, job, user_profile)
            st.markdown(f"**{label}**")
            st.code(filled, language=None)


def _render_job_card(row, show_match=False):
    """Render a single job card with optional match indicators."""
    with st.container(border=True):
        # Title + match badge
        pct = row.get("match_pct")
        has_match = show_match and pct is not None and not pd.isna(pct)
        if has_match:
            st.markdown(f"### {row['title']}  ·  `{int(pct)}% match`")
        else:
            st.markdown(f"### {row['title']}")
            if show_match:
                st.caption("_Not enough extracted skills to score this job reliably_")

        st.markdown(
            f"**{row['company']}** · {row['location']} · "
            f"{row['experience_level']} · "
            f"{row['salary_range_lpa'] or '—'} LPA · "
            f"{row['employment_type'] or '—'}"
        )

        if row.get("published_date"):
            st.caption(f"📅 Posted: {row['published_date']}")

        # Experience — NaN-safe
        exp_lo = row.get("experience_min")
        exp_hi = row.get("experience_max")
        has_lo = exp_lo is not None and not pd.isna(exp_lo)
        has_hi = exp_hi is not None and not pd.isna(exp_hi)
        if has_lo or has_hi:
            lo = int(exp_lo) if has_lo else "?"
            hi = int(exp_hi) if has_hi else "?"
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

        _render_referral_section(row)

        # ---------- Applied Tracker ----------
        job_url = (row.get("url") or "").rstrip("/")
        apps = load_applications()
        applied = apps.get(job_url)

        col_a, col_b = st.columns([2, 1])
        with col_a:
            if applied:
                st.success(f"✅ Applied on {applied.get('applied_date', '?')}")
            else:
                key = f"apply_{abs(hash(job_url))}"
                if st.button("📝 Mark as Applied", key=key):
                    add_application(dict(row))
                    st.rerun()
        with col_b:
            if job_url:
                st.markdown(f"[Apply →]({job_url})")

        if applied:
            key = f"rm_{abs(hash(job_url))}"
            if st.button("Remove from applied", key=key):
                remove_application(job_url)
                st.rerun()


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

    # Header row
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
        st.caption(f"Total: **{len(df)}** jobs")
    with c4:
        a_stats = app_stats()
        st.caption(f"📝 Applied: **{a_stats['total']}**")

    # ---------- Your Profile ----------
    with st.expander("🎯 Your Profile — skills + outreach info", expanded=False):
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

        st.markdown("**For referral outreach (optional)**")
        col3, col4 = st.columns(2)
        with col3:
            user_name = st.text_input(
                "Your full name", value="", key="user_name",
            )
            user_college = st.text_input(
                "Your college (for alumni search)",
                value="", key="user_college",
            )
        with col4:
            user_pitch = st.text_input(
                "One-line pitch",
                value="",
                key="user_pitch",
                placeholder="e.g. AI/ML engineer building RAG systems",
            )

        st.session_state["_user_profile"] = {
            "name": user_name,
            "college": user_college,
            "pitch": user_pitch,
            "skills": user_skills,
        }

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

    if f_fresh != "All time":
        days_map = {"Last 7 days": 7, "Last 14 days": 14, "Last 30 days": 30}
        days = days_map[f_fresh]
        cutoff = (pd.Timestamp.now() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
        filtered = filtered[filtered["published_date"] >= cutoff]

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

    # ---------- Best Matches ----------
    if user_skills and f_sort == "Best match" and not filtered.empty:
        st.divider()
        st.subheader("⭐ Best matches for you")
        top = filtered[
            filtered["match_pct"].notna()
            & (filtered["match_pct"] >= 40)
            & (filtered["matched_skills"].apply(lambda x: len(x) >= 2))
        ].head(10)
        if top.empty:
            st.info(
                "No strong matches yet. Add more skills to your profile, "
                "or relax the filters above."
            )
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
# PAGE: ATS CHECKER
# ============================================================

def page_ats():
    st.title("📄 ATS Checker")
    st.caption("Upload your resume → see which jobs you're ATS-ready for")

    st.subheader("1. Upload your resume (PDF)")
    uploaded = st.file_uploader("Resume PDF", type=["pdf"], key="resume_file")

    if uploaded is not None:
        file_bytes = uploaded.read()
        file_hash = str(hash(file_bytes))

        if st.session_state.get("_resume_hash") != file_hash:
            try:
                with st.spinner("Parsing resume..."):
                    text = extract_pdf_text(file_bytes)
                    skills = extract_skills_from_text(text)
                    st.session_state["_resume_hash"] = file_hash
                    st.session_state["_resume_text"] = text
                    st.session_state["_resume_skills"] = skills
            except Exception as e:
                st.error(f"Failed to parse PDF: {e}")
                return

    resume_text = st.session_state.get("_resume_text")
    resume_skills = st.session_state.get("_resume_skills")

    if not resume_text:
        st.info("⬆️ Upload your resume to see ATS analysis.")
        return

    st.success(
        f"✅ Resume parsed — {count_words(resume_text):,} words, "
        f"{len(resume_skills)} skills detected"
    )

    with st.expander("📊 Resume Analysis", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**Skills detected**")
            if resume_skills:
                skill_list = sorted(resume_skills.keys(), key=lambda x: -resume_skills[x])
                st.write(", ".join(skill_list))
            else:
                st.warning("No skills detected. Check PDF is text-based (not scanned).")
        with c2:
            st.markdown("**Contact info**")
            contacts = detect_contact_info(resume_text)
            for k, v in contacts.items():
                st.markdown(f"{'✅' if v else '❌'} {k.title()}")
        with c3:
            st.markdown("**Resume stats**")
            words = count_words(resume_text)
            st.write(f"Words: {words}")
            if 250 <= words <= 900:
                st.success("Length: optimal")
            elif words < 250:
                st.warning("Too short")
            else:
                st.warning("Very long")

    st.divider()
    st.subheader("2. Compute ATS scores")

    if st.button("🔄 Compute ATS for all jobs", key="ats_compute_all"):
        jobs = jobs_df()
        if jobs.empty:
            st.warning("No enriched jobs available.")
            return
        with st.spinner(f"Analyzing {len(jobs)} jobs..."):
            reports = []
            for _, job in jobs.iterrows():
                rep = compute_ats_report(resume_text, resume_skills, job.to_dict())
                reports.append(rep)
            jobs = jobs.copy()
            jobs["_ats_score"] = [r["score"] for r in reports]
            jobs["_ats_report"] = reports
            st.session_state["_ats_jobs"] = jobs
        st.success(f"Computed ATS for {len(jobs)} jobs")

    if "_ats_jobs" not in st.session_state:
        st.info("Click 'Compute ATS for all jobs' to see top matches.")
        return

    jobs_scored = st.session_state["_ats_jobs"]

    st.divider()
    st.subheader("⭐ Jobs you're ATS-ready for")

    c1, c2, c3 = st.columns([2, 2, 2])

    with c1:
        min_score = st.slider(
            "Minimum ATS score",
            min_value=0, max_value=100, value=50, step=5,
            key="ats_min_score",
        )
    with c2:
        role_filter = st.selectbox(
            "Role",
            ["All"] + sorted(jobs_scored["role_category"].unique().tolist()),
            key="ats_role",
        )
    with c3:
        sort_by = st.selectbox(
            "Sort",
            ["Best ATS match", "Newest first"],
            key="ats_sort",
        )

    filtered = jobs_scored[jobs_scored["_ats_score"] >= min_score].copy()
    if role_filter != "All":
        filtered = filtered[filtered["role_category"] == role_filter]

    if sort_by == "Best ATS match":
        filtered = filtered.sort_values("_ats_score", ascending=False)
    else:
        filtered = filtered.sort_values("published_date", ascending=False)

    st.caption(f"**{len(filtered)}** jobs match (ATS ≥ {min_score}%)")

    filter_key = f"{min_score}|{role_filter}|{sort_by}"
    if st.session_state.get("_ats_filter_key") != filter_key:
        st.session_state["_ats_filter_key"] = filter_key
        st.session_state["ats_show"] = 30

    if "ats_show" not in st.session_state:
        st.session_state["ats_show"] = 30

    show_n = min(st.session_state["ats_show"], len(filtered))

    for _, job in filtered.head(show_n).iterrows():
        report = job["_ats_report"]

        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"### {job['title']}")
                st.markdown(
                    f"**{job['company']}** · {job['location']} · "
                    f"{job['experience_level']} · {job['salary_range_lpa'] or '—'} LPA"
                )
            with c2:
                score = report["score"]
                if score >= 75:
                    st.success(f"ATS: {score}%")
                elif score >= 50:
                    st.warning(f"ATS: {score}%")
                else:
                    st.error(f"ATS: {score}%")

            if report["matched_required"]:
                st.markdown("**✓ You have:** " + ", ".join(report["matched_required"]))
            if report["missing_required"]:
                st.markdown("**✗ Missing:** " + ", ".join(report["missing_required"]))

            with st.expander("💡 Suggestions"):
                if report["missing_required"]:
                    st.markdown(
                        f"**Add these keywords to your resume:** "
                        f"{', '.join(report['missing_required'])}"
                    )
                if report["word_count"] < 250:
                    st.markdown("**Resume too short** — add more detail")
                if not report["contacts"]["linkedin"]:
                    st.markdown("**Add LinkedIn URL** to your resume header")
                if not report["contacts"]["github"]:
                    st.markdown("**Add GitHub URL** — critical for AI roles")

            st.markdown(f"[Apply →]({job['url']})")

    if show_n < len(filtered):
        remaining = len(filtered) - show_n
        if st.button(f"⬇ Load {min(30, remaining)} more ({remaining} remaining)"):
            st.session_state["ats_show"] += 30
            st.rerun()

    st.divider()
    st.subheader("🎓 Skills that most improve your ATS score")

    missing_counter = {}
    for _, job in jobs_scored.iterrows():
        for skill in job["_ats_report"]["missing_required"]:
            missing_counter[skill] = missing_counter.get(skill, 0) + 1

    if missing_counter:
        top_gaps = sorted(missing_counter.items(), key=lambda x: -x[1])[:15]
        gap_df = pd.DataFrame(
            [{"skill": s, "jobs_unlocked": n} for s, n in top_gaps]
        )
        fig = px.bar(
            gap_df, x="jobs_unlocked", y="skill", orientation="h",
            color="jobs_unlocked", color_continuous_scale="Reds",
            text="jobs_unlocked",
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(
            height=500, yaxis=dict(autorange="reversed"),
            coloraxis_showscale=False,
            margin=dict(l=0, r=40, t=10, b=10),
        )
        st.plotly_chart(fig, width='stretch')


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
# PAGE: ASK AI (RAG)
# ============================================================

def page_ask_ai():
    st.title("🤖 Ask AI")
    st.caption("Ask anything about the Indian AI career ecosystem — answers grounded in 2,265 indexed articles & jobs")

    if not RAG_AVAILABLE:
        st.error(f"RAG not available: {_rag_err_msg}")
        st.info("Make sure `rag_indexer.py` has been run at least once, and Gemini API key is set.")
        return

    # Sample questions
    with st.expander("💡 Sample questions", expanded=False):
        st.markdown("""
- Which Indian AI startups are working on RAG?
- What skills are required for AI/ML Engineer roles in Bangalore?
- What is happening in India's AI ecosystem regarding LLMs?
- Which companies are hiring for agentic AI?
- What salaries are typical for GenAI engineers in India?
        """)

    # Query input
    question = st.text_input(
        "Your question",
        key="rag_question",
        placeholder="e.g. Which Indian startups are working on RAG?",
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        ask = st.button("🔍 Ask", type="primary")
    with col2:
        top_k = st.slider("Sources to retrieve", 3, 15, 8, 1, key="rag_top_k")

    if ask and question.strip():
        with st.spinner("Retrieving + generating answer..."):
            try:
                answer, sources = rag_query_fn(question.strip(), top_k=top_k)
            except Exception as e:
                st.error(f"Query failed: {e}")
                return

        st.divider()
        st.subheader("Answer")
        st.markdown(answer)

        if sources:
            st.divider()
            st.subheader(f"📚 Sources ({len(sources)})")
            for i, s in enumerate(sources, start=1):
                badge = "📰" if s["type"] == "article" else "💼"
                with st.container(border=True):
                    st.markdown(f"**{badge} {s['title']}**")
                    meta_parts = []
                    if s.get("company"):
                        meta_parts.append(s["company"])
                    if s.get("location"):
                        meta_parts.append(s["location"])
                    if s.get("date"):
                        meta_parts.append(s["date"])
                    if meta_parts:
                        st.caption(" · ".join(meta_parts))
                    if s.get("url"):
                        st.markdown(f"[Open →]({s['url']})")


# ============================================================
# ROUTER
# ============================================================

if page == "Overview":
    page_overview()
elif page == "Jobs":
    page_jobs()
elif page == "Ask AI":
    page_ask_ai()
elif page == "ATS Checker":
    page_ats()
elif page == "Skills":
    page_skills()
elif page == "Companies":
    page_companies()
elif page == "Locations":
    page_locations()
elif page == "News":
    page_news()