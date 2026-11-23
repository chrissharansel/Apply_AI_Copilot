import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..config import settings
from ..database.models import log_audit, public
from ..database.mongodb import get_db
from ..services import conflicts as cf
from ..services.resume_match import recommend
from ..services.resume_service import reparse, save_upload
from ..utils.security import current_user

router = APIRouter(prefix="/resumes", tags=["resumes"])


class ResumeMeta(BaseModel):
    label: str | None = Field(None, max_length=80)          # e.g. "Python Developer"
    category: str | None = Field(None, max_length=60)       # e.g. "Backend"
    keywords: list[str] | None = None                       # extra terms that should pull this resume in
    job_type: str | None = Field(None, max_length=60)
    target_role: str | None = Field(None, max_length=100)
    effective_from: str | None = Field(None, max_length=20)
    effective_until: str | None = Field(None, max_length=20)


class JobIn(BaseModel):
    title: str = ""
    description: str = ""
    job_type: str = ""


async def _conflict_count(uid: str, resume: dict) -> int:
    prof = await get_db().candidate_profiles.find_one({"user_id": uid})
    if not prof or not resume.get("parsed"):
        return 0
    return len([c for c in cf.detect(prof["data"], resume["parsed"], prof.get("decisions")) if c["kind"] != "missing_in_resume"])


@router.post("")
async def upload(file: UploadFile = File(...), label: str = Form(""), category: str = Form(""), keywords: str = Form(""),
                 job_type: str = Form(""), target_role: str = Form(""), effective_from: str = Form(""), effective_until: str = Form(""),
                 user=Depends(current_user)):
    data = await file.read(settings.max_resume_mb * 1024 * 1024 + 1)
    try:
        doc = await save_upload(user["_id"], file.filename or "resume", data, label, category, [k for k in keywords.split(",")],
                                job_type, target_role, effective_from, effective_until)
    except ValueError as e:
        raise HTTPException(400, str(e))
    await log_audit(user["_id"], "resume_upload", resume_id=doc["_id"])
    return {**public(doc, hide=("text",)), "conflicts": await _conflict_count(user["_id"], doc)}


@router.get("")
async def list_resumes(user=Depends(current_user)):
    docs = await get_db().resumes.find({"user_id": user["_id"]}).sort("version", -1).to_list(100)
    return [public(d, hide=("text",)) for d in docs]


@router.put("/{rid}")
async def update_meta(rid: str, body: ResumeMeta, user=Depends(current_user)):
    col = get_db().resumes
    existing = await col.find_one({"_id": rid, "user_id": user["_id"]})
    if not existing:
        raise HTTPException(404, "Resume not found")
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    if "keywords" in upd:
        upd["keywords"] = [k.strip() for k in upd["keywords"] if k.strip()][:20]
    if "job_type" in upd and upd["job_type"] != (existing.get("job_type") or "other"):
        family = upd["job_type"] or "other"
        await col.update_many({"user_id": user["_id"], "job_type": family}, {"$set": {"job_type_active": False}})
        upd["job_type_active"] = True
        upd["family_version"] = (await col.count_documents({"user_id": user["_id"], "job_type": family})) + 1
    await col.update_one({"_id": rid, "user_id": user["_id"]}, {"$set": upd})
    return public(await col.find_one({"_id": rid}), hide=("text",))


@router.post("/recommend")
async def recommend_resume(body: JobIn, user=Depends(current_user)):
    """Which of my resumes fits this job description best, and why?"""
    rec = await recommend(user["_id"], {"title": body.title, "description": body.description, "job_type": body.job_type})
    if not rec:
        raise HTTPException(400, "Upload a resume first.")
    return rec


@router.post("/{rid}/activate")
async def activate(rid: str, user=Depends(current_user)):
    col = get_db().resumes
    if not await col.find_one({"_id": rid, "user_id": user["_id"]}):
        raise HTTPException(404, "Resume not found")
    await col.update_many({"user_id": user["_id"]}, {"$set": {"active": False}})
    await col.update_one({"_id": rid}, {"$set": {"active": True}})
    family = doc.get("job_type") or "other"
    await col.update_many({"user_id": user["_id"], "job_type": family}, {"$set": {"job_type_active": False}})
    await col.update_one({"_id": rid}, {"$set": {"job_type_active": True}})
    return {"ok": True}


@router.delete("/{rid}")
async def delete(rid: str, user=Depends(current_user)):
    col = get_db().resumes
    doc = await col.find_one({"_id": rid, "user_id": user["_id"]})
    if not doc:
        raise HTTPException(404, "Resume not found")
    Path(doc["storage_path"]).unlink(missing_ok=True)
    await col.delete_one({"_id": rid})
    remaining = await col.find({"user_id": user["_id"]}).sort("version", -1).to_list(100)
    if doc.get("active") and remaining:
        await col.update_one({"_id": remaining[0]["_id"]}, {"$set": {"active": True}})
    if doc.get("job_type_active"):
        family = doc.get("job_type") or "other"
        family_next = next((r for r in remaining if (r.get("job_type") or "other") == family), None)
        if family_next:
            await col.update_one({"_id": family_next["_id"]}, {"$set": {"job_type_active": True}})
    await log_audit(user["_id"], "resume_delete", resume_id=rid)
    return {"ok": True}


@router.post("/{rid}/reparse")
async def reparse_resume(rid: str, user=Depends(current_user)):
    """Re-read the stored file (links, header, text boxes) and re-extract. Doesn't touch your confirmed profile."""
    doc = await get_db().resumes.find_one({"_id": rid, "user_id": user["_id"]})
    if not doc:
        raise HTTPException(404, "Resume not found")
    doc = await reparse(doc)
    return {**public(doc, hide=("text",)), "conflicts": await _conflict_count(user["_id"], doc)}
