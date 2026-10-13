"""
Application tracker — simple JSON store for jobs you've applied to.

Stored in data/applications.json (personal — recommend gitignoring).
"""

import json
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APPS_FILE = PROJECT_ROOT / "data" / "applications.json"


def _load():
    if not APPS_FILE.exists():
        return {}
    try:
        with open(APPS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(data):
    APPS_FILE.parent.mkdir(exist_ok=True)
    temp = APPS_FILE.with_suffix(".tmp")
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    temp.replace(APPS_FILE)


def load_applications():
    return _load()


def is_applied(url):
    return (url or "").rstrip("/") in _load()


def add_application(job):
    data = _load()
    url = (job.get("url") or "").rstrip("/")
    if not url:
        return
    data[url] = {
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "location": job.get("location", ""),
        "applied_date": datetime.now().strftime("%Y-%m-%d"),
        "status": "applied",
        "notes": "",
    }
    _save(data)


def remove_application(url):
    data = _load()
    url = (url or "").rstrip("/")
    if url in data:
        del data[url]
        _save(data)


def stats():
    data = _load()
    by_status = {}
    for app in data.values():
        s = app.get("status", "applied")
        by_status[s] = by_status.get(s, 0) + 1
    return {"total": len(data), "by_status": by_status}