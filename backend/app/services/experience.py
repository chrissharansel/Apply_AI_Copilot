"""Experience calculation from saved employment / internship records, and picking the RIGHT category for a form question.
Principles: overlapping jobs are never double counted (union of month ranges); internships are tracked separately;
we never overstate (integer-only boxes get the floor); skill-specific years are estimates and are only ever suggested."""
import math
import re
from datetime import date

from .facts import norm

MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
PRESENT = re.compile(r"\b(present|current|now|ongoing|till date|to date|today)\b", re.I)
INTERN_RE = re.compile(r"\b(intern|internship|trainee|apprentice)\b", re.I)
CATEGORY_LABEL = {"total": "total experience (jobs and internships)", "professional": "professional experience (excluding internships)",
                  "internship": "internship experience", "current_role": "time in your current role"}


def _idx(y: int, m: int) -> int:
    return y * 12 + m - 1


def parse_month(s: str, end: bool = False, today: date | None = None):
    """-> ((year, month), approx) or None. 'Present' -> today. Year-only dates are flagged approximate."""
    today = today or date.today()
    t = (s or "").strip().lower()
    if not t:
        return None
    if PRESENT.search(t):
        return (today.year, today.month), False
    y = re.search(r"\b((?:19|20)\d{2})\b", t)
    if not y:
        return None
    year, mon = int(y.group(1)), None
    for name, i in MONTHS.items():
        if re.search(rf"\b{name}[a-z]*\b", t):
            mon = i
            break
    if mon is None:
        m = re.search(r"\b(\d{1,2})\s*[/\-.]\s*(?:19|20)\d{2}\b", t) or re.search(r"\b(?:19|20)\d{2}\s*[/\-.]\s*(\d{1,2})\b", t)
        if m and 1 <= int(m.group(1)) <= 12:
            mon = int(m.group(1))
    approx = mon is None
    return (year, mon or (12 if end else 1)), approx


def kind_of(rec: dict) -> str:
    if INTERN_RE.search(rec.get("title") or ""):
        return "internship"
    return (rec.get("kind") or "full_time").lower().replace("-", "_").replace(" ", "_")


def _union(ivs: list[tuple[int, int]]) -> int:
    """Total months covered by inclusive [start, end] month ranges, overlaps counted once."""
    total, cur = 0, None
    for s, e in sorted(ivs):
        if cur is None or s > cur[1] + 1:
            if cur:
                total += cur[1] - cur[0] + 1
            cur = [s, e]
        else:
            cur[1] = max(cur[1], e)
    return total + (cur[1] - cur[0] + 1 if cur else 0)


def calculate(employment: list[dict], today: date | None = None) -> dict:
    today = today or date.today()
    now_i = _idx(today.year, today.month)
    recs, warnings, approx_any = [], [], False
    for r in employment or []:
        name = r.get("company") or r.get("title") or "a position"
        s = parse_month(r.get("start_date", ""), False, today)
        if not s:
            warnings.append(f"“{name}” has no readable start date, so it isn't counted.")
            continue
        e = parse_month(r["end_date"], True, today) if (r.get("end_date") or "").strip() else ((today.year, today.month), False)
        if not e:
            warnings.append(f"“{name}” has an end date I can't read, so it isn't counted.")
            continue
        si, ei = _idx(*s[0]), min(_idx(*e[0]), now_i)
        if ei < si:
            warnings.append(f"“{name}” ends before it starts, so it isn't counted.")
            continue
        approx = s[1] or e[1]
        approx_any |= approx
        current = not (r.get("end_date") or "").strip() or bool(PRESENT.search(r.get("end_date", "")))
        recs.append({"company": r.get("company", ""), "cnorm": norm(r.get("company", "")), "title": r.get("title", ""), "kind": kind_of(r),
                     "start": si, "end": ei, "months": ei - si + 1, "approx": approx, "current": current,
                     "text": " ".join([r.get("title") or "", r.get("company") or "", r.get("description") or ""])})
    pro = [(x["start"], x["end"]) for x in recs if x["kind"] != "internship"]
    intern = [(x["start"], x["end"]) for x in recs if x["kind"] == "internship"]
    cur = [x for x in recs if x["current"] and x["kind"] != "internship"]
    if approx_any:
        warnings.append("Some dates have only a year, so totals are approximate. Add months for precision.")
    return {"total_years": round(_union(pro + intern) / 12, 2), "professional_years": round(_union(pro) / 12, 2),
            "internship_years": round(_union(intern) / 12, 2),
            "current_role_years": round(max((x["months"] for x in cur), default=0) / 12, 2),
            "records": [{k: v for k, v in x.items() if k != "text"} for x in recs], "_recs": recs, "warnings": warnings,
            "complete": len(recs) == len(employment or []) and bool(recs)}


def _mentions(text: str, term: str) -> bool:
    t = re.escape(norm(term)).replace(r"\ ", r"\s+")
    return bool(t) and bool(re.search(rf"(?<![a-z0-9]){t}(?![a-z0-9])", norm(text) if re.search(r"[a-z0-9]", term, re.I) else text.lower()))


def skill_years(calc: dict, term: str) -> tuple[float, list[str]]:
    hits = [x for x in calc["_recs"] if _mentions(x["text"], term) or _mentions(x["text"], term.replace(".", ""))]
    return round(_union([(x["start"], x["end"]) for x in hits]) / 12, 2), [x["cnorm"] for x in hits]


# ----------------------------------------------------------------------------- which category does the form ask for?
GENERIC = set("total overall professional relevant work working industry full time fulltime hands on handson practical related the your of years "
              "year yrs months month experience in with using on do you have how many much long are is at least minimum a an and or".split())
ASKS_YEARS = re.compile(r"\b(years?|yrs?|months?|how many|how long)\b", re.I)
IS_EXP = re.compile(r"experience|worked|working|how many years", re.I)


def experience_key(label: str, hint: str = "") -> str | None:
    """-> 'exp:total' | 'exp:professional' | 'exp:internship' | 'exp:current_role' | 'exp:skill:<term>' | None"""
    t = f"{label} {hint}".lower()
    if not (IS_EXP.search(t) and ASKS_YEARS.search(t)):
        return None
    if re.search(r"describe|tell us|explain|list your", t):
        return None
    if re.search(r"\bintern", t):
        return "exp:internship"
    if re.search(r"(current|present)\s+(role|company|employer|position|job|organi[sz]ation)|in your current|at your current", t):
        return "exp:current_role"
    m = (re.search(r"(?:experience|years?|yrs?)\s+(?:of\s+)?(?:with|in|using|on|of|as)\s+([^?(),:;]{2,40})", t) or
         re.search(r"([a-z][a-z0-9+#.\-]*(?:\s+[a-z][a-z0-9+#.\-]*){0,2})\s+(?:experience|exp\b)", label.lower()))
    if m:
        words = [w for w in re.split(r"\s+", m.group(1).strip(" .-")) if w and w not in GENERIC]
        if words:
            return "exp:skill:" + " ".join(words[:3])
    if re.search(r"professional|relevant|industry|full[- ]?time|paid", t):
        return "exp:professional"
    return "exp:total"


def unit_of(label: str, hint: str = "") -> str:
    t = f"{label} {hint}".lower()
    return "months" if re.search(r"\bmonths?\b", t) and not re.search(r"\byears?\b|\byrs?\b", t) else "years"


def years_for(profile: dict, calc: dict, pk: str) -> dict | None:
    """-> {years, note, fact_paths, estimate} or None when nothing reliable can be said."""
    stated = profile.get("total_experience_years")
    manual = profile.get("experience_mode") == "manual"
    cat = "total" if pk == "total_experience" else pk.split(":", 2)[1]
    if cat in ("total", "professional") and stated is not None and (manual or not calc["complete"]):
        why = "the total you entered" if manual else "the total from your resume (some job dates couldn't be read)"
        return {"years": float(stated), "note": f"{why}", "fact_paths": ["total_experience_years"], "estimate": False, "cat": cat}
    if not calc["_recs"]:
        return None
    paths = lambda recs: [f"employment:{x['cnorm']}" for x in recs]
    if cat in ("total", "professional", "internship"):
        key = {"total": "total_years", "professional": "professional_years", "internship": "internship_years"}[cat]
        use = [x for x in calc["_recs"] if cat == "total" or (x["kind"] == "internship") == (cat == "internship")]
        return {"years": calc[key], "note": f"calculated from your work history: {CATEGORY_LABEL[cat]}", "fact_paths": paths(use), "estimate": False, "cat": cat}
    if cat == "current_role":
        cur = [x for x in calc["_recs"] if x["current"] and x["kind"] != "internship"]
        return {"years": calc["current_role_years"], "note": f"calculated from your current role start date", "fact_paths": paths(cur), "estimate": False, "cat": cat} if cur else None
    term = pk.split(":", 2)[2]
    y, c = skill_years(calc, term)
    if not c:
        return None
    return {"years": y, "note": f"estimated from the {len(c)} job(s) in your history that mention “{term}”", "fact_paths": [f"employment:{x}" for x in c], "estimate": True, "cat": "skill"}


# ----------------------------------------------------------------------------- writing the number into a form
def format_years(years: float, kind: str, step: str = "", unit: str = "years") -> str:
    v = years * 12 if unit == "months" else years
    integer_only = kind == "number" and (not step or re.fullmatch(r"\d+", step.strip() or "1") is not None) or unit == "months"
    if integer_only or float(v).is_integer():
        return str(int(math.floor(v + 1e-9)))                  # never overstate
    return str(math.floor(v * 10 + 1e-9) / 10)


def _range(label: str):
    t = label.lower().replace("–", "-").replace("—", "-").replace(",", "")
    unit = 1 / 12 if "month" in t and "year" not in t else 1
    num = r"(\d+(?:\.\d+)?)"
    if re.search(r"fresher|no experience|^none$|^zero", t.strip()):
        return (0.0, 0.5)
    if m := re.search(rf"{num}\s*(?:-|to)\s*{num}", t):
        return (float(m.group(1)) * unit, float(m.group(2)) * unit)
    if m := (re.search(rf"{num}\s*\+", t) or re.search(rf"(?:more than|over|above|at least|>=?)\s*{num}", t) or re.search(rf"{num}\s*(?:or more|and above|and over|or above)", t)):
        return (float(next(g for g in m.groups() if g)) * unit, None)
    if m := re.search(rf"(?:less than|under|below|<)\s*{num}", t):
        return (0.0, float(m.group(1)) * unit)
    if m := re.fullmatch(rf"\D*{num}\s*(?:years?|yrs?|months?)?\D*", t.strip()):
        n = float(m.group(1)) * unit
        return (n, n + 1 * unit)
    return None


def numeric_option(years: float, options: list[dict]) -> dict | None:
    rs = [(o, _range(o["label"])) for o in options]
    rs = [(o, r) for o, r in rs if r]
    for o, (lo, hi) in rs:                                     # lo <= years < hi (open-ended: no hi)
        if years >= lo and (hi is None or years < hi):
            return o
    fl = math.floor(years)
    for o, (lo, hi) in rs:                                     # gaps like "1-2", "3-4": fall back to the floor
        if fl >= lo and (hi is None or fl <= hi):
            return o
    return None
