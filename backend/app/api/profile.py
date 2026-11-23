import asyncio
import shutil
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..agents.orchestrator import manager
from ..config import settings
from ..database.models import log_audit, new_id, now, public
from ..database.mongodb import get_db
from ..schemas.profile import ProfileData, ProfileUpdate
from ..services import conflicts as cf
from ..services import experience as ex
from ..services import facts
from ..services.resume_service import classify_links, read_file
from ..utils.security import current_user

router = APIRouter(prefix="/profile", tags=["profile"])


async def _load(uid: str) -> dict | None:
    """Profile with fact metadata; profiles from before fact tracking are migrated on first read."""
    p = await get_db().candidate_profiles.find_one({"user_id": uid})
    if p and p.get("facts") is None:
        p["facts"] = facts.migrate(p)
        await get_db().candidate_profiles.update_one({"_id": p["_id"]}, {"$set": {"facts": p["facts"]}})
    return p


def _out(p: dict | None) -> dict:
    if not p:
        return {"data": ProfileData().model_dump(), "confirmed": False, "confirmed_at": None, "facts": [], "summary": {}}
    rows = facts.describe(p["data"], p.get("facts") or {})
    summary = {"confirmed": sum(r["status"] == "confirmed" for r in rows), "needs_confirmation": sum(r["status"] in ("needs_confirmation", "stale") for r in rows),
               "missing": sum(r["status"] == "missing" and r.get("core") for r in rows)}
    return {**public(p, hide=("decisions",)), "facts": rows, "fact_meta": {k: {"source": v["source"], "confidence": v["confidence"]} for k, v in (p.get("facts") or {}).items()}, "summary": summary}


@router.get("")
async def get_profile(user=Depends(current_user)):
    return _out(await _load(user["_id"]))


@router.put("")
async def put_profile(body: ProfileUpdate, user=Depends(current_user)):
    old = await _load(user["_id"])
    data = body.data.model_dump()
    meta = facts.update_on_save((old or {}).get("data") or {}, (old or {}).get("facts") or {}, data, body.confirm)
    await get_db().candidate_profiles.update_one(
        {"user_id": user["_id"]},
        {"$set": {"data": data, "facts": meta, "confirmed": body.confirm or bool(old and old.get("confirmed")), "updated_at": now(),
                  **({"confirmed_at": now()} if body.confirm else {})},
         "$setOnInsert": {"_id": new_id(), "user_id": user["_id"], "decisions": {}}}, upsert=True)
    await log_audit(user["_id"], "profile_confirm" if body.confirm else "profile_save")
    return _out(await _load(user["_id"]))


@router.post("/from-resume/{rid}")
async def from_resume(rid: str, user=Depends(current_user)):
    """Loads a resume's extracted data as an UNVERIFIED draft: every value is marked 'from resume' until you confirm it."""
    r = await get_db().resumes.find_one({"_id": rid, "user_id": user["_id"]})
    if not r:
        raise HTTPException(404, "Resume not found")
    await get_db().candidate_profiles.update_one(
        {"user_id": user["_id"]},
        {"$set": {"data": r["parsed"], "facts": facts.from_resume(r["parsed"], r.get("link_fields", []), rid), "confirmed": False,
                  "confirmed_at": None, "source_resume_id": rid, "updated_at": now()},
         "$setOnInsert": {"_id": new_id(), "user_id": user["_id"], "decisions": {}}}, upsert=True)
    return _out(await _load(user["_id"]))


@router.post("/refresh-links")
async def refresh_links(overwrite: bool = False, user=Depends(current_user)):
    """Pull LinkedIn/GitHub/portfolio/email from the clickable links inside the active resume (no AI involved).
    Fills empty fields only; if the resume disagrees with the profile it reports a conflict instead of overwriting."""
    db = get_db()
    r = await db.resumes.find_one({"user_id": user["_id"], "active": True})
    if not r:
        raise HTTPException(400, "Upload a resume first.")
    text, links = await asyncio.to_thread(read_file, r)
    await db.resumes.update_one({"_id": r["_id"]}, {"$set": {"links": links[:60]}})
    c = classify_links(links, text)
    prof = await _load(user["_id"])
    data = (prof or {}).get("data") or ProfileData().model_dump()
    meta = dict((prof or {}).get("facts") or {})
    added, conflicts = [], {}
    for k in ("linkedin", "github", "portfolio", "email", "phone"):
        if not c[k]:
            continue
        if not data.get(k) or overwrite:
            if data.get(k) != c[k]:
                data[k] = c[k]
                meta[k] = facts.entry("user_confirmed" if overwrite else "resume_link", r["_id"])
                added.append(k)
        elif data[k].rstrip("/").lower() != c[k].rstrip("/").lower():
            conflicts[k] = c[k]
    others = list(data.get("other_links") or [])
    have = {o["url"].lower() for o in others} | {str(data.get(k, "")).lower() for k in ("linkedin", "github", "portfolio")}
    for o in c["other_links"] + c["generic"]:
        if o["url"].lower() not in have:
            others.append(o)
            have.add(o["url"].lower())
            added.append(o["label"])
    data["other_links"] = others[:15]
    if added and data["other_links"]:
        meta["other_links"] = facts.entry("resume_link", r["_id"])
    if added or not prof:       # profile stays as confirmed as before; the NEW values are individually marked unconfirmed
        await db.candidate_profiles.update_one(
            {"user_id": user["_id"]}, {"$set": {"data": data, "facts": meta, "updated_at": now()},
                                       "$setOnInsert": {"_id": new_id(), "user_id": user["_id"], "confirmed": False, "decisions": {}}}, upsert=True)
    return {"profile": _out(await _load(user["_id"])), "added": added, "conflicts": conflicts, "links_in_file": len(links)}


# ----------------------------------------------------------------------------- experience
@router.get("/experience")
async def experience(user=Depends(current_user)):
    p = await _load(user["_id"])
    data = (p or {}).get("data") or {}
    calc = ex.calculate(data.get("employment") or [])
    stated = data.get("total_experience_years")
    skills = []
    for s in (data.get("skills") or [])[:25]:
        y, hits = ex.skill_years(calc, s)
        if hits:
            skills.append({"skill": s, "years": y, "jobs": len(hits)})
    return {"total_years": calc["total_years"], "professional_years": calc["professional_years"], "internship_years": calc["internship_years"],
            "current_role_years": calc["current_role_years"], "stated_years": stated, "mode": data.get("experience_mode", "calculated"),
            "records": calc["records"], "warnings": calc["warnings"], "complete": calc["complete"],
            "skills": sorted(skills, key=lambda x: -x["years"]),
            "differs": stated is not None and calc["complete"] and abs(calc["total_years"] - float(stated)) > 0.75}


# ----------------------------------------------------------------------------- conflicts
class Resolution(BaseModel):
    id: str
    choice: str                  # profile | resume | custom
    value: str | None = None


class ResolveIn(BaseModel):
    resume_id: str | None = None
    resolutions: list[Resolution]


async def _resume_for(uid: str, rid: str | None) -> dict | None:
    q = {"_id": rid, "user_id": uid} if rid else {"user_id": uid, "active": True}
    return await get_db().resumes.find_one(q)


@router.get("/conflicts")
async def conflicts(resume_id: str | None = None, user=Depends(current_user)):
    p, r = await _load(user["_id"]), await _resume_for(user["_id"], resume_id)
    if not p or not r:
        return {"resume": None, "conflicts": []}
    return {"resume": {"id": r["_id"], "label": r.get("label") or r["filename"]}, "conflicts": cf.detect(p["data"], r["parsed"], p.get("decisions"))}


@router.post("/conflicts/resolve")
async def resolve(body: ResolveIn, user=Depends(current_user)):
    db = get_db()
    p, r = await _load(user["_id"]), await _resume_for(user["_id"], body.resume_id)
    if not p or not r:
        raise HTTPException(404, "Nothing to resolve")
    live = {c["id"]: c for c in cf.detect(p["data"], r["parsed"], p.get("decisions"))}
    old_data = p["data"]
    data = ProfileData(**old_data).model_dump()
    decisions, touched = dict(p.get("decisions") or {}), []
    for x in body.resolutions:
        c = live.get(x.id)
        if not c:
            continue
        if x.choice == "custom" and not (x.value or "").strip():
            raise HTTPException(400, "Enter the correct value.")
        t = cf.apply(data, c, x.choice, (x.value or "").strip())
        touched.append(t)
        decisions[x.id] = {"resume": c["resume"], "choice": x.choice, "at": now()}
    meta = facts.update_on_save(old_data, p.get("facts") or {}, data, False)
    snap = facts.snapshot(data)
    for path in touched:                                    # the user just ruled on these: they are now confirmed facts
        if path and path in snap:
            meta[path] = facts.entry("user_confirmed", r["_id"])
    for x in body.resolutions:                              # employment/education/cert rows touched by id prefix
        c = live.get(x.id)
        if c and c["target"].get("type") == "item" and not (x.choice == "profile" and c["kind"] == "new_in_resume"):
            for path in snap:
                if path.split(":", 1)[-1].split("#")[0] == facts.norm(c["target"]["match"]) or facts.norm(c["target"]["match"]) in path:
                    meta[path] = facts.entry("user_confirmed", r["_id"])
    await db.candidate_profiles.update_one({"user_id": user["_id"]}, {"$set": {"data": data, "facts": meta, "decisions": decisions, "updated_at": now()}})
    await log_audit(user["_id"], "conflicts_resolved", count=len(body.resolutions))
    return _out(await _load(user["_id"]))


@router.delete("/data")
async def delete_everything(delete_account: bool = False, user=Depends(current_user)):
    """Right to erasure: removes profile, resumes (files too), knowledge base, applications and history."""
    uid, db = user["_id"], get_db()
    for sid in [s["_id"] async for s in db.agent_sessions.find({"user_id": uid}, {"_id": 1})]:
        t = manager.tasks.get(sid)
        if t:
            t.cancel()
        shutil.rmtree(Path(settings.storage_dir) / "screenshots" / sid, ignore_errors=True)
    shutil.rmtree(Path(settings.storage_dir) / "resumes" / uid, ignore_errors=True)
    for c in ("candidate_profiles", "resumes", "knowledge_base", "applications", "application_questions",
              "agent_sessions", "interaction_history"):
        await db[c].delete_many({"user_id": uid})
    if delete_account:
        await db.users.delete_one({"_id": uid})
        await db.audit_logs.delete_many({"user_id": uid})
    else:
        await log_audit(uid, "data_deleted")
    return {"ok": True}
