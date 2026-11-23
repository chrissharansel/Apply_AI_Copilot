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
    s = 0.65 * coverage + 0.30 * align + min(0.05, 0.025 * kw_hit)
    return {"id": resume["_id"], "label": resume.get("label") or resume["filename"], "category": resume.get("category", ""),
            "score": round(s, 3), "matched": matched[:12], "title_match": sorted(title_t & label_t)}


TIE_SYSTEM = """You choose which resume version to send for a job. Candidates are the same person's resumes for different job categories.
Choose the one whose focus best matches the job's main requirements. Reply JSON {"index": <number>, "reason": "<one short sentence>"}."""


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
            r = await llm.chat_json(TIE_SYSTEM, json.dumps({"job": {"title": job.get("title"), "description": (job.get("description") or "")[:2500]},
                "resumes": [{"index": i, "label": c["label"], "category": c["category"], "skills": (by_id[c["id"]].get("parsed") or {}).get("skills", [])[:25],
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
