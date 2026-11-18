from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ..agents.orchestrator import manager
from ..config import settings
from ..database.models import log_audit, new_id, now, public
from ..database.mongodb import get_db
from ..schemas.agent import AnswerIn, ApproveIn, StartSession
from ..services import application_service as apps
from ..services import knowledge_service as kb
from ..services.browser_service import bm
from ..services.llm_service import llm
from ..utils.security import current_user
from ..utils.validators import validate_job_url

router = APIRouter(prefix="/agent", tags=["agent"])


async def _own(sid: str, uid: str) -> dict:
    s = await get_db().agent_sessions.find_one({"_id": sid, "user_id": uid})
    if not s:
        raise HTTPException(404, "Session not found")
    return s


async def _msg(s: dict, role: str, text: str, kind: str = "answer") -> None:
    await get_db().interaction_history.insert_one({"_id": new_id(), "session_id": s["_id"], "user_id": s["user_id"],
                                                   "role": role, "kind": kind, "text": text, "meta": {}, "ts": now()})


@router.get("/health")
async def health(user=Depends(current_user)):
    return await llm.health()


@router.post("/sessions")
async def start(body: StartSession, user=Depends(current_user)):
    uid, db = user["_id"], get_db()
    try:
        url = await validate_job_url(body.url)
    except ValueError as e:
        raise HTTPException(400, str(e))
    prof = await db.candidate_profiles.find_one({"user_id": uid})
    if not prof or not prof.get("confirmed"):
        raise HTTPException(400, "Review and confirm your profile first. The agent only uses confirmed information.")
    q = {"_id": body.resume_id, "user_id": uid} if body.resume_id else {"user_id": uid, "active": True}
    resume = await db.resumes.find_one(q)
    if not resume:
        raise HTTPException(400, "Upload a resume first.")
    if manager.active_count(uid) >= 2 or manager.active_count() >= settings.max_concurrent_sessions:
        raise HTTPException(429, "Too many applications running. Finish or cancel one first.")
    sid = new_id()
    aid = await apps.create_application(uid, url, sid, resume)
    await db.agent_sessions.insert_one({
        "_id": sid, "user_id": uid, "url": url, "resume_id": resume["_id"], "application_id": aid,
        "status": "Pending", "state": "INIT", "progress": 0, "job": {}, "collected": {}, "pending_questions": [],
        "results": [], "review": None, "approval": None, "step": 0, "error": None, "resumable": False,
        "created_at": now(), "updated_at": now()})
    await log_audit(uid, "session_start", session_id=sid, host=url.split("/")[2])
    manager.launch(sid, uid)
    return {"id": sid}


@router.get("/sessions")
async def list_sessions(user=Depends(current_user)):
    docs = await get_db().agent_sessions.find({"user_id": user["_id"]}, {"results": 0, "collected": 0}).sort("created_at", -1).to_list(50)
    return [public(d) for d in docs]


@router.get("/sessions/{sid}")
async def get_session(sid: str, user=Depends(current_user)):
    s = await _own(sid, user["_id"])
    msgs = await get_db().interaction_history.find({"session_id": sid}).sort("ts", 1).to_list(300)
    out = public(s, hide=("collected",))
    out["messages"] = [public(m) for m in msgs]
    out["running"] = manager.running(sid)
    return out


@router.post("/sessions/{sid}/answers")
async def answer(sid: str, body: AnswerIn, user=Depends(current_user)):
    s = await _own(sid, user["_id"])
    q = next((x for x in s.get("pending_questions", []) if x["qid"] == body.qid and x["status"] == "open"), None)
    if not q:
        raise HTTPException(409, "That question is no longer waiting for an answer.")
    db = get_db()
    upd: dict = {}
    if q["manual"]:
        if body.action != "done":
            raise HTTPException(400, "Complete the step in the browser, then press Done.")
        if q["key"].startswith("manual_"):
            await _msg(s, "user", "Done.")
        else:
            upd[f"collected.{q['key']}"] = {"manual_done": True, "skip": True}
            await _msg(s, "user", f"Done: {q['label']}")
        status = "answered"
    elif body.action == "skip":
        if q["required"]:
            raise HTTPException(400, "This question is required.")
        upd[f"collected.{q['key']}"] = {"skip": True}
        await _msg(s, "user", "Skip this one.")
        status = "skipped"
    else:
        value = body.answer
        if value in (None, "", []):
            raise HTTPException(400, "Enter an answer or skip.")
        if isinstance(value, list):
            value = [str(v)[:500] for v in value][:30]
        else:
            value = str(value).strip()[:4000]
        upd[f"collected.{q['key']}"] = {"value": value, "skip": False}
        shown = ", ".join(value) if isinstance(value, list) else value
        await _msg(s, "user", shown)
        if body.save != "no":
            await kb.save_answer(user["_id"], q["label"], shown, category=q["category"], source="user", verified=True,
                                 reusable=body.save == "reusable", application_id=s["application_id"] if body.save == "job_only" else None)
            await _msg(s, "agent", "Saved for future applications." if body.save == "reusable" else "Saved for this application only.", "activity")
        status = "answered"
    await db.agent_sessions.update_one({"_id": sid}, {"$set": {**upd, "pending_questions.$[q].status": status, "updated_at": now()}},
                                       array_filters=[{"q.qid": body.qid}])
    return {"ok": True}


@router.post("/sessions/{sid}/approve")
async def approve(sid: str, body: ApproveIn, user=Depends(current_user)):
    s = await _own(sid, user["_id"])
    if s["status"] != "Ready for Review" or not manager.running(sid):
        raise HTTPException(409, "This application isn't waiting for approval.")
    await get_db().agent_sessions.update_one({"_id": sid}, {"$set": {"approval": {"approved": True, "edits": body.edits, "at": now()}}})
    await log_audit(user["_id"], "submission_approved", session_id=sid)
    await _msg(s, "user", "Approved. Submit it.")
    return {"ok": True}


@router.post("/sessions/{sid}/cancel")
async def cancel(sid: str, user=Depends(current_user)):
    s = await _own(sid, user["_id"])
    await get_db().agent_sessions.update_one({"_id": sid}, {"$set": {"status": "Cancelled", "updated_at": now()}})
    await apps.set_status(s["application_id"], "Cancelled")
    if not manager.running(sid):
        await bm.close(sid)
    return {"ok": True}


@router.post("/sessions/{sid}/resume")
async def resume(sid: str, user=Depends(current_user)):
    s = await _own(sid, user["_id"])
    if manager.running(sid):
        raise HTTPException(409, "Already running.")
    if s["status"] not in ("Requires Manual Intervention", "Failed"):
        raise HTTPException(409, "Only stopped applications can be resumed.")
    if manager.active_count() >= settings.max_concurrent_sessions:
        raise HTTPException(429, "Too many applications running.")
    await get_db().agent_sessions.update_one({"_id": sid}, {"$set": {"status": "Pending", "error": None, "approval": None,
                                                                    "pending_questions": [], "state": "INIT", "updated_at": now()}})
    manager.launch(sid, user["_id"])
    return {"ok": True}


@router.get("/sessions/{sid}/screenshot")
async def screenshot(sid: str, user=Depends(current_user)):
    await _own(sid, user["_id"])
    await bm.screenshot(sid)
    p = Path(settings.storage_dir) / "screenshots" / sid / "latest.png"
    if not p.exists():
        raise HTTPException(404, "No snapshot yet")
    return FileResponse(p, media_type="image/png", headers={"Cache-Control": "no-store"})
