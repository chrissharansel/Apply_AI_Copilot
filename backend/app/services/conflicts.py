"""Compare what a resume says with the saved profile. Differences are shown to the user; nothing is overwritten silently."""
import re
from difflib import SequenceMatcher

from . import experience as ex
from .facts import norm

SCALAR_CHECKS = [("full_name", "Full name", "high", norm), ("email", "Email", "high", lambda v: (v or "").lower().strip()),
                 ("phone", "Phone number", "high", lambda v: re.sub(r"\D", "", v or "")[-10:]),
                 ("location", "Location", "low", lambda v: norm((v or "").split(",")[0])),
                 ("current_designation", "Current designation", "medium", norm),
                 ("linkedin", "LinkedIn", "medium", lambda v: norm(re.sub(r"https?://(www\.)?", "", v or ""))),
                 ("github", "GitHub", "medium", lambda v: norm(re.sub(r"https?://(www\.)?", "", v or ""))),
                 ("portfolio", "Portfolio", "medium", lambda v: norm(re.sub(r"https?://(www\.)?", "", v or "")))]


def _same_name(a: str, b: str) -> bool:
    a, b = norm(a), norm(b)
    return bool(a and b) and (a == b or (min(len(a), len(b)) >= 4 and (a in b or b in a)) or SequenceMatcher(None, a, b).ratio() >= 0.82)


def _find(name: str, rows: list[dict], key: str) -> dict | None:
    return next((r for r in rows if _same_name(name, r.get(key, ""))), None)


def _month(s: str, end: bool):
    p = ex.parse_month(s, end)
    return p[0] if p else None


def _date_view(s: str) -> str:
    return (s or "").strip() or "(blank)"


def detect(profile: dict, parsed: dict, decisions: dict | None = None) -> list[dict]:
    decisions, out = decisions or {}, []

    def add(cid, label, kind, sev, pv, rv, target, raw):
        if decisions.get(cid, {}).get("resume") == str(rv):          # the user already ruled on THIS resume value
            return
        out.append({"id": cid, "label": label, "kind": kind, "severity": sev, "profile": str(pv), "resume": str(rv), "target": target, "resume_raw": raw})

    for f, label, sev, key in SCALAR_CHECKS:
        pv, rv = (profile.get(f) or "").strip(), (parsed.get(f) or "").strip()
        if rv and not pv:
            add(f"scalar:{f}", label, "new_in_resume", "low", "", rv, {"type": "scalar", "field": f}, rv)
        elif rv and pv and key(pv) != key(rv):
            add(f"scalar:{f}", label, "different", sev, pv, rv, {"type": "scalar", "field": f}, rv)

    for pe in parsed.get("employment") or []:
        c = norm(pe.get("company"))
        if not c:
            continue
        mine = _find(pe.get("company", ""), profile.get("employment") or [], "company")
        name = pe.get("company")
        if not mine:
            add(f"employment:{c}:*", f"Employer “{name}”", "new_in_resume", "medium", "", f"{pe.get('title','')} ({_date_view(pe.get('start_date'))} to {_date_view(pe.get('end_date'))})",
                {"type": "item", "coll": "employment", "match": name, "field": "*"}, pe)
            continue
        if pe.get("title") and mine.get("title") and not _same_name(pe["title"], mine["title"]):
            add(f"employment:{c}:title", f"{name}: job title", "different", "medium", mine["title"], pe["title"], {"type": "item", "coll": "employment", "match": name, "field": "title"}, pe["title"])
        for fld, end in (("start_date", False), ("end_date", True)):
            a, b = (mine.get(fld) or "").strip(), (pe.get(fld) or "").strip()
            if not b and not a:
                continue
            ma, mb = _month(a, end) if a else ((9999, 12) if end else None), _month(b, end) if b else ((9999, 12) if end else None)
            if (a or b) and ma != mb and not (end and not a and ex.PRESENT.search(b or "")) and not (end and not b and ex.PRESENT.search(a or "")):
                add(f"employment:{c}:{fld}", f"{name}: {'start' if not end else 'end'} date", "different", "high", _date_view(a), _date_view(b),
                    {"type": "item", "coll": "employment", "match": name, "field": fld}, b)
    for mine in profile.get("employment") or []:
        if mine.get("company") and not _find(mine["company"], parsed.get("employment") or [], "company") and (parsed.get("employment") or []):
            out.append({"id": f"employment:{norm(mine['company'])}:missing", "label": f"Employer “{mine['company']}”", "kind": "missing_in_resume", "severity": "low",
                        "profile": f"{mine.get('title','')}", "resume": "(not on this resume)", "target": {"type": "info"}, "resume_raw": None})

    for pe in parsed.get("education") or []:
        n = pe.get("institution")
        if not norm(n):
            continue
        mine = _find(n, profile.get("education") or [], "institution")
        if not mine:
            add(f"education:{norm(n)}:*", f"Education “{n}”", "new_in_resume", "low", "", f"{pe.get('degree','')} {pe.get('graduation_year','')}".strip(), {"type": "item", "coll": "education", "match": n, "field": "*"}, pe)
        elif pe.get("graduation_year") and mine.get("graduation_year") and str(pe["graduation_year"]).strip() != str(mine["graduation_year"]).strip():
            add(f"education:{norm(n)}:graduation_year", f"{n}: graduation year", "different", "medium", mine["graduation_year"], pe["graduation_year"],
                {"type": "item", "coll": "education", "match": n, "field": "graduation_year"}, pe["graduation_year"])
    for pc in parsed.get("certifications") or []:
        if norm(pc.get("name")) and not _find(pc["name"], profile.get("certifications") or [], "name"):
            add(f"certifications:{norm(pc['name'])}:*", f"Certification “{pc['name']}”", "new_in_resume", "low", "", pc.get("issuer", ""), {"type": "item", "coll": "certifications", "match": pc["name"], "field": "*"}, pc)

    stated = parsed.get("total_experience_years")
    calc = ex.calculate(profile.get("employment") or [])
    if stated is not None and calc["complete"] and abs(calc["total_years"] - float(stated)) > 0.75:
        add("experience:total", "Total experience", "different", "medium", f"{calc['total_years']} years (calculated from your jobs)", f"{stated} years (stated on resume)",
            {"type": "experience"}, float(stated))
    return out


def apply(data: dict, c: dict, choice: str, custom: str | None = None) -> str | None:
    """Apply one resolution to the profile data in place. Returns the profile path touched (or None)."""
    t = c["target"]
    if t["type"] == "info":
        return None
    if choice == "profile" and t["type"] != "experience":
        return t["field"] if t["type"] == "scalar" else None        # keeping my value = confirming my value
    value = custom if choice == "custom" else c["resume_raw"]
    if t["type"] == "scalar":
        data[t["field"]] = value
        return t["field"]
    if t["type"] == "experience":
        if choice == "profile":
            data["experience_mode"] = "calculated"
        else:
            data["total_experience_years"], data["experience_mode"] = float(value), "manual"
        return "total_experience_years"
    rows = data.setdefault(t["coll"], [])
    namekey = {"employment": "company", "education": "institution", "certifications": "name"}[t["coll"]]
    mine = _find(t["match"], rows, namekey)
    if t["field"] == "*":
        if not mine:
            rows.append(dict(c["resume_raw"]))
        return None
    if mine:
        mine[t["field"]] = value
    return None
