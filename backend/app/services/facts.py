"""Fact confidence: every candidate detail carries a SOURCE and a CONFIDENCE, so the agent can tell what is safe to type
into a form (confirmed by you) from what is merely a suggestion (read off a resume, or typed but never confirmed)."""
import json
import re
from datetime import datetime

from ..database.models import now

SCALARS = ["full_name", "email", "phone", "location", "city", "state", "country", "postal_code", "address", "current_designation",
           "total_experience_years", "summary", "linkedin", "github", "portfolio", "desired_role", "expected_salary",
           "employment_type", "notice_period", "work_authorization", "availability"]
LISTS = ["skills", "languages", "other_links", "preferred_locations"]
ITEMS = {"employment": ("employment", "company"), "education": ("education", "institution"),
         "certifications": ("certification", "name"), "projects": ("project", "name")}
CORE = ["full_name", "email", "phone", "location", "current_designation", "skills"]
OPTIONAL = ["linkedin", "github", "portfolio", "notice_period", "expected_salary", "work_authorization"]

TRUSTED_SOURCES = {"user_confirmed", "approved", "calculated"}
CONFIDENCE = {"user_confirmed": 1.0, "approved": 0.9, "calculated": 0.9, "user_entered": 0.8, "resume_link": 0.85, "resume": 0.6, "unverified": 0.3, "missing": 0.0}
SOURCE_LABEL = {"user_confirmed": "Confirmed by you", "approved": "Approved answer", "calculated": "Calculated from your history",
                "user_entered": "Typed by you, not confirmed", "resume_link": "From a link in your resume", "resume": "Read from your resume",
                "unverified": "Unverified", "missing": "Missing"}
TTL_DAYS = {"notice_period": 90, "expected_salary": 90, "availability": 60, "work_authorization": 180}
LABELS = {"full_name": "Full name", "email": "Email", "phone": "Phone", "location": "Location", "city": "City", "state": "State", "country": "Country",
          "postal_code": "Postal code", "address": "Address", "current_designation": "Current designation", "total_experience_years": "Total experience (stated)",
          "summary": "Summary", "linkedin": "LinkedIn", "github": "GitHub", "portfolio": "Portfolio", "desired_role": "Desired role",
          "expected_salary": "Expected salary", "employment_type": "Employment type", "notice_period": "Notice period",
          "work_authorization": "Work authorization", "availability": "Availability", "skills": "Skills", "languages": "Languages",
          "other_links": "Other links", "preferred_locations": "Preferred locations"}

# profile-key (from the form analyzer) -> the fact that backs it
KEY_TO_FACT = {"first_name": "full_name", "last_name": "full_name", "full_name": "full_name", "email": "email", "phone": "phone",
               "linkedin": "linkedin", "github": "github", "portfolio": "portfolio", "location": "location", "city": "city", "state": "state",
               "country": "country", "postal_code": "postal_code", "address": "address", "current_title": "current_designation",
               "skills": "skills", "summary": "summary", "languages": "languages", "notice_period": "notice_period",
               "expected_salary": "expected_salary", "employment_type": "employment_type", "availability": "availability",
               "work_authorization": "work_authorization"}
# keys whose form value IS the whole fact, so a user's answer can safely update the profile
DIRECT_KEYS = {"email": "email", "phone": "phone", "linkedin": "linkedin", "github": "github", "portfolio": "portfolio", "location": "location",
               "city": "city", "state": "state", "country": "country", "postal_code": "postal_code", "address": "address",
               "current_title": "current_designation", "summary": "summary"}


def norm(s) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", str(s or "").lower())).strip()


def snapshot(d: dict) -> dict[str, str]:
    """Flatten a profile into {fact path: comparable string}. List items get stable paths like employment:acme corp."""
    out: dict[str, str] = {}
    for k in SCALARS:
        v = d.get(k)
        if v not in (None, ""):
            out[k] = str(v).strip()
    for k in LISTS:
        if d.get(k):
            out[k] = json.dumps(d[k], sort_keys=True, ensure_ascii=False)
    for coll, (singular, namekey) in ITEMS.items():
        seen: dict[str, int] = {}
        for row in d.get(coll) or []:
            n = norm(row.get(namekey))
            if not n:
                continue
            seen[n] = seen.get(n, 0) + 1
            path = f"{singular}:{n}" + (f"#{seen[n]}" if seen[n] > 1 else "")
            out[path] = json.dumps({k: v for k, v in row.items() if k != namekey}, sort_keys=True, ensure_ascii=False)
    return out


def entry(source: str, resume_id: str | None = None) -> dict:
    return {"source": source, "confidence": CONFIDENCE[source], "updated_at": now(), "resume_id": resume_id}


def update_on_save(old_data: dict, old_meta: dict, new_data: dict, confirm: bool) -> dict:
    """User edited/saved the profile. Changed values are theirs; 'confirm' vouches for everything on the page."""
    old, new, meta = snapshot(old_data), snapshot(new_data), {}
    for p, v in new.items():
        prev = old_meta.get(p)
        if confirm:
            meta[p] = entry("user_confirmed")
        elif prev and old.get(p) == v:
            meta[p] = prev
        else:
            meta[p] = entry("user_entered")
    return meta


def from_resume(parsed: dict, link_fields: list[str], resume_id: str) -> dict:
    return {p: entry("resume_link" if p in link_fields else "resume", resume_id) for p in snapshot(parsed)}


def migrate(prof: dict) -> dict:
    """Profiles created before fact tracking: confirmed profile => user_confirmed, otherwise read from resume."""
    src = "user_confirmed" if prof.get("confirmed") else "resume"
    t = prof.get("confirmed_at") or prof.get("updated_at")
    meta = {p: entry(src) for p in snapshot(prof.get("data") or {})}
    if t:
        for e in meta.values():
            e["updated_at"] = t
    return meta


def trusted(e: dict | None, path: str = "") -> bool:
    if not e or e.get("source") not in TRUSTED_SOURCES or e.get("confidence", 0) < 0.8:
        return False
    ttl = TTL_DAYS.get(path)
    return not (ttl and e.get("updated_at") and (now() - e["updated_at"]).days > ttl)


def explain(e: dict | None, path: str = "") -> str:
    if not e:
        return "not yet confirmed"
    if e.get("source") in TRUSTED_SOURCES:
        return f"you last confirmed it {(now() - e['updated_at']).days} days ago" if e.get("updated_at") else "needs a recheck"
    return {"resume": "read from your resume, not yet confirmed", "resume_link": "from a link in your resume, not yet confirmed",
            "user_entered": "typed by you but not confirmed"}.get(e.get("source"), "unverified")


def fact_path(p: dict, key: str) -> str | None:
    if key.startswith("link:"):
        return "other_links"
    if key in ("city", "state", "country") and not p.get(key):
        return "location"                                       # derived from the location string
    if key in KEY_TO_FACT:
        return KEY_TO_FACT[key]
    snap = snapshot(p)
    if key == "current_company":
        for row in p.get("employment") or []:
            if (row.get("end_date") or "").strip().lower() in ("", "present", "current", "now"):
                path = f"employment:{norm(row.get('company'))}"
                return path if path in snap else None
    if key in ("university", "degree", "graduation_year") and p.get("education"):
        path = f"education:{norm(p['education'][0].get('institution'))}"
        return path if path in snap else None
    return None


def describe(data: dict, meta: dict) -> list[dict]:
    """Rows for the UI: every fact with source, confidence and status; plus important facts that are MISSING."""
    snap, rows = snapshot(data), []
    for path, val in snap.items():
        e = meta.get(path)
        ok = trusted(e, path)
        src = e["source"] if e else "unverified"
        status = "confirmed" if ok else ("stale" if e and e.get("source") in TRUSTED_SOURCES else "needs_confirmation")
        label = LABELS.get(path) or (path.split(":")[0].title() + ": " + path.split(":", 1)[1].split("#")[0])
        rows.append({"path": path, "label": label, "value": val[:90], "source": src, "source_label": SOURCE_LABEL.get(src, src),
                     "confidence": e["confidence"] if e else CONFIDENCE["unverified"], "status": status,
                     "updated_at": e.get("updated_at") if e else None})
    for p in CORE + OPTIONAL:
        if p not in snap:
            rows.append({"path": p, "label": LABELS[p], "value": "", "source": "missing", "source_label": "Missing", "confidence": 0.0,
                         "status": "missing", "core": p in CORE, "updated_at": None})
    for coll, label in (("employment", "Employment history"), ("education", "Education")):
        if not any(r["path"].startswith(coll[:-1] if coll == "education" else coll) for r in rows if r["status"] != "missing") and not (data.get(coll)):
            rows.append({"path": coll, "label": label, "value": "", "source": "missing", "source_label": "Missing", "confidence": 0.0, "status": "missing", "core": True, "updated_at": None})
    return rows
