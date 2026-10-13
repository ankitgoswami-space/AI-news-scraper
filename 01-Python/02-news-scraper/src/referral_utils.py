"""
Referral utilities — LinkedIn search URLs + outreach templates.

No LinkedIn scraping (banned by LinkedIn ToS).
Only generates search URLs + copy-paste templates for manual use.
"""

from urllib.parse import quote_plus


def linkedin_people_search(keywords):
    """Build a LinkedIn people-search URL."""
    return (
        f"https://www.linkedin.com/search/results/people/"
        f"?keywords={quote_plus(keywords)}"
    )


def build_linkedin_searches(job, user_college=""):
    """
    Return list of (label, url) LinkedIn search suggestions for a job.
    Ordered by usefulness.
    """
    company = (job.get("company") or "").strip()
    title = (job.get("title") or "").strip()
    location = (job.get("location") or "").strip()
    city = location.split(",")[0].strip() if location else ""

    searches = []

    if company and title:
        searches.append((
            f"🎯 People with similar role at {company}",
            linkedin_people_search(f"{company} {title}"),
        ))

    if company:
        searches.append((
            f"👔 Recruiters at {company}",
            linkedin_people_search(f"{company} recruiter"),
        ))

    if company:
        searches.append((
            f"👥 HR / Talent at {company}",
            linkedin_people_search(f"{company} HR"),
        ))

    if company and city:
        searches.append((
            f"📍 People at {company} in {city}",
            linkedin_people_search(f"{company} {city}"),
        ))

    if company and user_college:
        searches.append((
            f"🎓 {user_college} alumni at {company}",
            linkedin_people_search(f"{user_college} {company}"),
        ))

    return searches


def format_template(template, job, user):
    """
    Fill placeholders in the template with job + user data.
    """
    skills = user.get("skills") or []
    skills_str = ", ".join(skills[:3]) if skills else "[your top 3 skills]"
    pitch = user.get("pitch") or ""

    result = template
    result = result.replace("[Company]", job.get("company") or "")
    result = result.replace("[Role]", job.get("title") or "")
    result = result.replace("[City]", (job.get("location") or "").split(",")[0].strip())
    result = result.replace("[YourName]", user.get("name") or "[Your Name]")
    result = result.replace("[Skills]", skills_str)
    result = result.replace("[College]", user.get("college") or "[Your College]")
    if pitch:
        result = result.replace("[Pitch]", pitch)
    return result


# ============================================================
# TEMPLATES — short, specific, not essays
# ============================================================

TEMPLATE_PEER = """Hi [Name],

I noticed [Company] is hiring a [Role]. I work on AI/ML projects with [Skills] and would love to learn more about your experience at [Company].

Would you be open to a 10-minute chat this week?

Thanks,
[YourName]"""


TEMPLATE_HR = """Hi [Name],

I'm reaching out regarding the [Role] role at [Company]. My background in [Skills] aligns closely with the requirements.

Could you point me to the right way to apply, or to someone on the team?

Thanks,
[YourName]"""


TEMPLATE_ALUMNI = """Hi [Name],

We're both from [College]. I saw [Company] is hiring a [Role] and would value your take on the team and the role.

Would you be open to a short chat when you have a moment?

Thanks,
[YourName]"""