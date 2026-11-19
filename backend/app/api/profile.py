import asyncio
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from ..agents.orchestrator import manager
from ..config import settings
from ..database.models import log_audit, new_id, now, public
from ..database.mongodb import get_db
from ..schemas.profile import ProfileData, ProfileUpdate
from ..services.resume_service import classify_links, read_file
from ..utils.security import current_user

router = APIRouter(prefix="/profile", tags=["profile"])


def _out(p: dict | None) -> dict:
    if not p:
        return {"data": ProfileData().model_dump(), "confirmed": False, "confirmed_at": None}
    return public(p)


@router.get("")
async def get_profile(user=Depends(current_user)):
    return _out(await get_db().candidate_profiles.find_one({"user_id": user["_id"]}))


@router.put("")
async def put_profile(body: ProfileUpdate, user=Depends(current_user)):
    fields = {"data": body.data.model_dump(), "confirmed": body.confirm, "updated_at": now(),
              "confirmed_at": now() if body.confirm else None}
    await get_db().candidate_profiles.update_one(
        {"user_id": user["_id"]}, {"$set": fields, "$setOnInsert": {"_id": new_id(), "user_id": user["_id"]}}, upsert=True)
    await log_audit(user["_id"], "profile_confirm" if body.confirm else "profile_save")
    return _out(await get_db().candidate_profiles.find_one({"user_id": user["_id"]}))


@router.post("/from-resume/{rid}")
async def from_resume(rid: str, user=Depends(current_user)):
    """Loads a resume's extracted data as an UNCONFIRMED draft. Nothing becomes authoritative until the user confirms."""
    r = await get_db().resumes.find_one({"_id": rid, "user_id": user["_id"]})
    if not r:
        raise HTTPException(404, "Resume not found")
    await get_db().candidate_profiles.update_one(
        {"user_id": user["_id"]},
        {"$set": {"data": r["parsed"], "confirmed": False, "confirmed_at": None, "source_resume_id": rid, "updated_at": now()},
         "$setOnInsert": {"_id": new_id(), "user_id": user["_id"]}}, upsert=True)
    return _out(await get_db().candidate_profiles.find_one({"user_id": user["_id"]}))


@router.post("/refresh-links")
async def refresh_links(overwrite: bool = False, user=Depends(current_user)):
    """Pull LinkedIn/GitHub/portfolio/email from the clickable links inside the active resume (no AI involved).
    Fills empty fields only; if the resume disagrees with what's in the profile it reports a conflict instead of overwriting."""
    db = get_db()
    r = await db.resumes.find_one({"user_id": user["_id"], "active": True})
    if not r:
        raise HTTPException(400, "Upload a resume first.")
    text, links = await asyncio.to_thread(read_file, r)
    await db.resumes.update_one({"_id": r["_id"]}, {"$set": {"links": links[:60]}})
    c = classify_links(links, text)
    prof = await db.candidate_profiles.find_one({"user_id": user["_id"]})
    data = (prof or {}).get("data") or ProfileData().model_dump()
    added, conflicts = [], {}
    for k in ("linkedin", "github", "portfolio", "email", "phone"):
        if not c[k]:
            continue
        if not data.get(k) or overwrite:
            if data.get(k) != c[k]:
                data[k] = c[k]
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
    if added or not prof:
        await db.candidate_profiles.update_one(
            {"user_id": user["_id"]},
            {"$set": {"data": data, "confirmed": False, "confirmed_at": None, "updated_at": now()},
             "$setOnInsert": {"_id": new_id(), "user_id": user["_id"]}}, upsert=True)
    return {"profile": _out(await db.candidate_profiles.find_one({"user_id": user["_id"]})), "added": added,
            "conflicts": conflicts, "links_in_file": len(links)}


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
