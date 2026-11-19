from pathlib import Path

import asyncio

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ..config import settings
from ..database.models import log_audit, public
from ..database.mongodb import get_db
from ..services.resume_service import reparse, save_upload
from ..utils.security import current_user

router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.post("")
async def upload(file: UploadFile = File(...), user=Depends(current_user)):
    data = await file.read(settings.max_resume_mb * 1024 * 1024 + 1)
    try:
        doc = await save_upload(user["_id"], file.filename or "resume", data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await log_audit(user["_id"], "resume_upload", resume_id=doc["_id"])
    return public(doc, hide=("text",))


@router.get("")
async def list_resumes(user=Depends(current_user)):
    docs = await get_db().resumes.find({"user_id": user["_id"]}).sort("version", -1).to_list(100)
    return [public(d, hide=("text",)) for d in docs]


@router.post("/{rid}/activate")
async def activate(rid: str, user=Depends(current_user)):
    col = get_db().resumes
    if not await col.find_one({"_id": rid, "user_id": user["_id"]}):
        raise HTTPException(404, "Resume not found")
    await col.update_many({"user_id": user["_id"]}, {"$set": {"active": False}})
    await col.update_one({"_id": rid}, {"$set": {"active": True}})
    return {"ok": True}


@router.delete("/{rid}")
async def delete(rid: str, user=Depends(current_user)):
    col = get_db().resumes
    doc = await col.find_one({"_id": rid, "user_id": user["_id"]})
    if not doc:
        raise HTTPException(404, "Resume not found")
    Path(doc["storage_path"]).unlink(missing_ok=True)
    await col.delete_one({"_id": rid})
    await log_audit(user["_id"], "resume_delete", resume_id=rid)
    return {"ok": True}


@router.post("/{rid}/reparse")
async def reparse_resume(rid: str, user=Depends(current_user)):
    """Re-read the stored file (links, header, text boxes) and re-extract details. Doesn't touch your confirmed profile."""
    doc = await get_db().resumes.find_one({"_id": rid, "user_id": user["_id"]})
    if not doc:
        raise HTTPException(404, "Resume not found")
    return public(await reparse(doc), hide=("text",))
