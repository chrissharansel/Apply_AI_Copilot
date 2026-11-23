"""Recommend the most relevant resume for a job. Deterministic scoring (explainable), with one optional LLM tie-break."""
import json
import re
from collections import Counter

from ..database.mongodb import get_db
from .llm_service import llm

STOP = set("""a an the and or of to in on for with at by from as is are be this that it its we you your our their will can should must may
about into over than then them they who what which when where why how all any each more most other such only own same so too very job role position
team work working experience years year strong ability skills skill knowledge good great excellent required requirements responsibilities
responsible preferred plus including include etc using use used build building develop developing development looking join company
candidate candidates opportunity help across within new high level well also able need needs must have has had been being""".split())
TOKEN = re.compile(r"[a-z][a-z0-9+#.\-]{1,}")


def terms(text: str) -> list[str]:
    return [t.strip(".-") for t in TOKEN.findall((text or "").lower()) if t.strip(".-") not in STOP and len(t.strip(".-")) > 1]



def infer_job_type(text: str) -> str:
    t = (text or "").lower()
    if any(x in t for x in ("machine learning", "data scientist", "llm", "analytics", "ai engineer", "data engineer")):
        return "data_ai"
    if any(x in t for x in ("devops", "cloud engineer", "kubernetes", "site reliability")):
        return "devops_cloud"
    if any(x in t for x in ("qa engineer", "test automation", "quality assurance", "software tester")):
        return "qa_testing"
    if any(x in t for x in ("frontend", "backend", "full stack", "software developer", "software engineer", "java developer", "python developer")):
        return "software_development"
    return "other"

def score(job: dict, resume: dict) -> dict:
    title_t = set(terms(job.get("title", "")))
    weights: Counter = Counter()
    for t in terms(job.get("description", "")):
        weights[t] += 1
    for t in title_t:
        weights[t] += 3
    top = dict(weights.most_common(45))
    rt = set(terms(resume.get("text", ""))) | {s.lower() for s in (resume.get("parsed") or {}).get("skills", [])}
    rt |= set(terms(" ".join(k for k in resume.get("keywords", []))))
    matched = [t for t in top if t in rt]
    coverage = sum(top[t] for t in matched) / sum(top.values()) if top else 0.0
    label_t = set(terms(" ".join([resume.get("label", ""), resume.get("category", ""), " ".join(resume.get("keywords", []))])))
    align = len(title_t & label_t) / len(title_t) if title_t else 0.0
    kw_hit = sum(1 for k in resume.get("keywords", []) if k.lower() in (job.get("description", "") + " " + job.get("title", "")).lower())
    requested_type = (job.get("job_type") or "").lower().replace("-", "_").replace(" ", "_")
    job_type = requested_type if requested_type not in ("", "other") else infer_job_type(job.get("title", "") + " " + job.get("description", ""))
    resume_type_raw = (resume.get("job_type") or "").lower().replace("-", "_").replace(" ", "_")
    resume_type = resume_type_raw if resume_type_raw not in ("", "other") else infer_job_type(
        " ".join([resume.get("target_role", ""), resume.get("label", ""),
                  (resume.get("parsed") or {}).get("desired_role", ""),
                  (resume.get("parsed") or {}).get("current_designation", "")]))
    type_match = 1.0 if job_type and resume_type == job_type else 0.0
    role = (job.get("title") or "").lower()
    generic_role_terms = {"developer", "engineer", "analyst", "specialist", "manager", "lead", "senior", "junior", "associate"}
    target_terms = set(terms(resume.get("target_role", ""))) - generic_role_terms
    target_match = 1.0 if target_terms and target_terms.intersection(set(terms(role))) else 0.0
    # A current version gets a small tie-break boost; it never outweighs skill relevance.
    from datetime import datetime, timezone
    created = resume.get("created_at")
    if isinstance(created, datetime):
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age_days = max(0, (datetime.now(timezone.utc) - created).days)
    else:
        age_days = 0
    recency = max(0.0, 1.0 - age_days / 730.0)
    today = datetime.now(timezone.utc).date().isoformat()
    starts_ok = not resume.get("effective_from") or resume["effective_from"] <= today
    ends_ok = not resume.get("effective_until") or resume["effective_until"] >= today
    effective_now = starts_ok and ends_ok
    family_default = bool(resume.get("job_type_active"))
    s = (0.53 * coverage + 0.21 * align + 0.12 * type_match + 0.06 * target_match
         + min(0.04, 0.02 * kw_hit) + 0.01 * recency
         + (0.02 if family_default else 0.0) + (0.01 if effective_now else -0.02))
    return {"id": resume["_id"], "label": resume.get("label") or resume["filename"], "category": resume.get("category", ""),
             "score": round(s, 3), "matched": matched[:12], "title_match": sorted(title_t & label_t),
             "job_type_match": bool(type_match), "target_role_match": bool(target_match), "effective_now": effective_now,
            "family_default": family_default, "version": resume.get("version"), "family_version": resume.get("family_version"),
            "created_at": resume.get("created_at")}


TIE_SYSTEM = """You select among versions of the same candidate's resume.
Prioritize evidence of required skills, the target role, job-family alignment and responsibilities.
Use effective dates only as a secondary consideration; a recent version must not beat a materially better skills match.
Do not infer skills that are not listed. If candidates are essentially tied, choose the family default.
Return JSON {"index": <number>, "reason": "<one evidence-based sentence>"}."""


async def recommend(user_id: str, job: dict, resumes: list[dict] | None = None, use_llm: bool = True) -> dict | None:
    resumes = resumes if resumes is not None else await get_db().resumes.find({"user_id": user_id}).to_list(100)
    if not resumes:
        return None
    ranking = sorted((score(job, r) for r in resumes), key=lambda x: -x["score"])
    best, close = ranking[0], len(ranking) > 1 and ranking[0]["score"] - ranking[1]["score"] < 0.07 and ranking[0]["score"] > 0
    reason = ""
    if close and use_llm and (job.get("title") or job.get("description")):
        try:
            by_id = {r["_id"]: r for r in resumes}
            cands = ranking[:3]
            r = await llm.chat_json(TIE_SYSTEM, json.dumps({"job": {"title": job.get("title"), "description": (job.get("description") or "")[:2500],
                         "job_type": (job.get("job_type") if job.get("job_type") not in (None, "", "other")
                                     else infer_job_type(job.get("title", "") + " " + job.get("description", "")))},
                "resumes": [{"index": i, "label": c["label"], "category": c["category"], "job_type": by_id[c["id"]].get("job_type", ""), "target_role": by_id[c["id"]].get("target_role", ""), "family_default": bool(by_id[c["id"]].get("job_type_active")),
                             "effective_from": by_id[c["id"]].get("effective_from", ""), "effective_until": by_id[c["id"]].get("effective_until", ""), "skills": (by_id[c["id"]].get("parsed") or {}).get("skills", [])[:25],
                             "headline": (by_id[c["id"]].get("parsed") or {}).get("current_designation", "")} for i, c in enumerate(cands)]}))
            i = r.get("index")
            if isinstance(i, int) and 0 <= i < len(cands):
                best, reason = cands[i], str(r.get("reason", ""))[:200]
                ranking = [best] + [x for x in ranking if x["id"] != best["id"]]
        except Exception:
            pass
    gap = best["score"] - (ranking[1]["score"] if len(ranking) > 1 and ranking[0] is best else 0)
    conf = "high" if best["score"] >= 0.35 and gap >= 0.07 else "medium" if best["score"] >= 0.2 else "low"
    if not reason:
        reason = (f"matches {', '.join(best['matched'][:6])}" if best["matched"] else "no strong match; using your default") + (
            f"; your “{best['label']}” focus fits the title" if best["title_match"] else "")
    return {"best": best["id"], "label": best["label"], "confidence": conf, "reason": reason, "ranking": ranking}
