"""Persistent memory. Distinguishes confirmed facts from AI suggestions and job-specific answers."""
import difflib
import re
from datetime import timedelta

from ..config import settings
from ..database.models import new_id, now, public
from ..database.mongodb import get_db
from .llm_service import llm

STOP = set("a an the are is am you your do does did to of for in on at be have has will would can could "
           "with this that if any please".split())

CATEGORY_RULES = [
    ("legal_declaration", r"\b(i|we) (agree|certify|acknowledge|consent|confirm|declare|understand)\b|terms (and|&) conditions|privacy (policy|notice)|i hereby|authori[sz]e (us|the company)|to the best of my knowledge"),
    ("sponsorship", r"sponsor"),
    ("work_authorization", r"authori[sz]|legally (able|eligible|entitled)|right to work|work permit|work visa|\bvisa\b|eligible to work"),
    ("citizenship", r"citizen|nationalit"),
    ("security_clearance", r"clearance"),
    ("criminal_record", r"convict|felony|criminal|misdemeanor"),
    ("non_compete", r"non-?compete|restrictive covenant"),
    ("gender", r"\bgender\b|pronoun"),
    ("race_ethnicity", r"\brace\b|ethnic|hispanic|latino"),
    ("veteran_status", r"veteran|military"),
    ("disability_status", r"disabilit"),
    ("sexual_orientation", r"sexual orientation|lgbt"),
    ("date_of_birth", r"date of birth|\bdob\b|birth ?date|\bage\b"),
    ("current_salary", r"(current|present|last|existing).{0,20}(salary|ctc|compensation|pay)|(salary|ctc|compensation).{0,15}(current|present|last drawn)"),
    ("salary_expectation", r"salary|\bctc\b|compensation|remuneration|pay expectation|expected pay|stipend"),
    ("notice_period", r"notice period|how soon can you|earliest.{0,20}(start|join)|serving notice"),
    ("availability", r"start date|available to start|when can you (start|join)|availability|date available"),
    ("relocation", r"relocat"),
    ("remote_preference", r"\bremote\b|hybrid|on-?site|work from home"),
    ("willing_to_travel", r"travel"),
    ("referral_source", r"how did you (hear|find|learn)|referr|where did you (hear|find)"),
    ("previous_employment", r"previously (applied|worked|employed)|(worked|employed) (for|at|with) .{0,40}before|former employee|current employee"),
    ("employment_type", r"full[- ]?time|part[- ]?time|\bcontract\b|employment type|job type"),
    ("languages", r"language"),
    ("education_grade", r"\bgpa\b|\bcgpa\b|percentage|\bgrade"),
]
_COMPILED = [(c, re.compile(p, re.I)) for c, p in CATEGORY_RULES]

# Never auto-answered from anything but a user-verified, fresh, exactly-matching saved answer.
SENSITIVE = {"legal_declaration", "sponsorship", "work_authorization", "citizenship", "security_clearance",
             "criminal_record", "non_compete", "gender", "race_ethnicity", "veteran_status",
             "disability_status", "sexual_orientation", "date_of_birth", "current_salary",
             "salary_expectation"}

TTL_DAYS = {"salary_expectation": 90, "current_salary": 90, "notice_period": 90, "availability": 60,
            "work_authorization": 180, "sponsorship": 180, "relocation": 180, "remote_preference": 180}
DEFAULT_TTL = 365


def normalize(q: str) -> str:
    q = re.sub(r"[^a-z0-9\s]", " ", (q or "").lower())
    return " ".join(w for w in q.split() if w not in STOP)


def answer_key(label: str, kind: str) -> str:
    words = "_".join(normalize(label).split())[:100]
    return f"{kind}_{words}" if words else kind


def categorize(text: str) -> str:
    for cat, rx in _COMPILED:
        if rx.search(text or ""):
            return cat
    return "other"


def jaccard(a: str, b: str) -> float:
    x, y = set(a.split()), set(b.split())
    return len(x & y) / len(x | y) if x and y else 0.0


def stem(w: str) -> str:
    """Crude stemmer: relocate/relocation/relocating -> 'reloca'; sponsor/sponsorship -> 'sponso'."""
    w = w.rstrip("s") if len(w) > 3 else w
    return w[:6]


def lex_score(a: str, b: str) -> float:
    """Lexical similarity of two NORMALIZED questions, 0..1 (no model involved)."""
    sa, sb = " ".join(stem(w) for w in a.split()), " ".join(stem(w) for w in b.split())
    return round(0.6 * jaccard(sa, sb) + 0.4 * difflib.SequenceMatcher(None, sa, sb).ratio(), 3)


def is_stale(doc: dict) -> bool:
    ts = doc.get("confirmed_at") or doc.get("updated_at")
    ttl = TTL_DAYS.get(doc.get("category", "other"), DEFAULT_TTL)
    return bool(ts and now() - ts > timedelta(days=ttl))


def annotate(doc: dict) -> dict:
    d = public(doc)
    d["stale"] = is_stale(doc)
    d["needs_confirmation"] = (not doc.get("verified")) or d["stale"]
    d["sensitive"] = doc.get("category") in SENSITIVE
    return d


async def save_answer(user_id: str, question: str, answer: str, *, category: str | None = None,
                      source: str = "user", verified: bool = True, reusable: bool = True,
                      application_id: str | None = None) -> str:
    qn = normalize(question)
    category = category or categorize(question)
    col = get_db().knowledge_base
    scope = {"user_id": user_id, "question_norm": qn, "application_id": None if reusable else application_id}
    existing = await col.find_one(scope)
    t = now()
    fields = {"question": question.strip(), "answer": answer, "category": category, "source": source,
              "verified": verified, "reusable": reusable, "updated_at": t, "confirmed_at": t if verified else None}
    if existing:
        await col.update_one({"_id": existing["_id"]}, {"$set": fields})
        return existing["_id"]
    doc = {"_id": new_id(), **scope, **fields, "created_at": t, "use_count": 0, "last_used_at": None}
    await col.insert_one(doc)
    return doc["_id"]


JUDGE_SYSTEM = """You compare a NEW job-application question with SAVED questions the candidate already answered.
Pick the saved question that asks for exactly the same information, so its saved answer would be a correct answer to the new question.
Be strict: a different country, role, time frame, amount, or a negation means it is NOT the same.
Reply JSON {"index": <number or null>}. Use null when unsure."""
_JUDGED: dict[tuple, int | None] = {}


async def _judge(user_id: str, question: str, cands: list[dict]) -> dict | None:
    """One Copilot call to confirm a paraphrase. Cached per process; failure just means 'no match'."""
    key = (user_id, normalize(question), tuple(c["_id"] for c in cands))
    if key not in _JUDGED:
        try:
            r = await llm.chat_json(JUDGE_SYSTEM, __import__("json").dumps(
                {"new_question": question, "saved_questions": [{"index": i, "question": c["question"]} for i, c in enumerate(cands)]}))
            i = r.get("index")
            _JUDGED[key] = i if isinstance(i, int) and 0 <= i < len(cands) else None
        except Exception:
            return None
    i = _JUDGED[key]
    return cands[i] if i is not None else None


async def find_answer(user_id: str, question: str, category: str | None = None) -> dict | None:
    """Exact match, then lexical similarity, then (only for plausible candidates) a strict Copilot paraphrase check."""
    category = category or categorize(question)
    qn = normalize(question)
    docs = await get_db().knowledge_base.find({"user_id": user_id, "reusable": True}).to_list(2000)
    best, score, mtype = None, 0.0, ""
    for d in docs:
        if d["question_norm"] == qn:
            best, score, mtype = d, 1.0, "exact"
            break
    if not best and docs:
        scored = []
        for d in docs:
            dc = d.get("category", "other")
            if category != "other" and dc != "other" and dc != category:
                continue                      # never cross categories (e.g. sponsorship vs authorization)
            scored.append((lex_score(qn, d["question_norm"]), d))
        scored.sort(key=lambda x: -x[0])
        if scored and scored[0][0] >= settings.similarity_threshold:
            score, best, mtype = scored[0][0], scored[0][1], "semantic"
        else:
            plausible = [d for s, d in scored if (s >= 0.2 and category != "other" and d.get("category") == category) or s >= 0.4][:3]
            if plausible and (hit := await _judge(user_id, question, plausible)):
                best, mtype = hit, "semantic"
                score = max(lex_score(qn, hit["question_norm"]), settings.similarity_threshold)
    if not best:
        return None

    cat = best.get("category", "other")
    sensitive = cat in SENSITIVE or category in SENSITIVE
    verified, stale = bool(best.get("verified")), is_stale(best)
    auto = verified and not stale and (mtype == "exact" or (not sensitive and score >= settings.similarity_threshold))
    reason = ("saved answer" if mtype == "exact" else f"similar saved question “{best['question']}”")
    if not verified:
        reason += ", not yet confirmed by you"
    elif stale:
        reason += ", last confirmed a while ago"
    elif sensitive and mtype != "exact":
        reason += ", sensitive questions need an exact match"
    return {"entry_id": best["_id"], "answer": best["answer"], "question": best["question"], "category": cat,
            "score": round(score, 3), "match_type": mtype, "verified": verified, "stale": stale,
            "sensitive": sensitive, "auto_use": auto,
            "confidence": round(score * (1 if verified else 0.4) * (0.6 if stale else 1), 3), "reason": reason}


async def touch(entry_id: str) -> None:
    await get_db().knowledge_base.update_one({"_id": entry_id}, {"$set": {"last_used_at": now()}, "$inc": {"use_count": 1}})


async def verified_facts(user_id: str, limit: int = 15) -> list[dict]:
    """Confirmed, reusable, non-sensitive answers the LLM may use as grounded context."""
    docs = await get_db().knowledge_base.find({"user_id": user_id, "verified": True, "reusable": True}).sort("updated_at", -1).to_list(60)
    return [{"question": d["question"], "answer": d["answer"]} for d in docs
            if d.get("category") not in SENSITIVE][:limit]
