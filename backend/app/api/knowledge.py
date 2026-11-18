from fastapi import APIRouter, Depends, HTTPException

from ..database.models import now
from ..database.mongodb import get_db
from ..schemas.application import KnowledgeIn, KnowledgeUpdate
from ..services import knowledge_service as kb
from ..utils.security import current_user

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("")
async def list_entries(category: str | None = None, needs_confirmation: bool = False, user=Depends(current_user)):
    q: dict = {"user_id": user["_id"]}
    if category:
        q["category"] = category
    docs = await get_db().knowledge_base.find(q).sort("updated_at", -1).to_list(1000)
    out = [kb.annotate(d) for d in docs]
    return [d for d in out if d["needs_confirmation"]] if needs_confirmation else out


@router.get("/categories")
async def categories():
    return sorted({c for c, _ in kb.CATEGORY_RULES} | {"other"})


@router.post("")
async def create(body: KnowledgeIn, user=Depends(current_user)):
    eid = await kb.save_answer(user["_id"], body.question, body.answer, category=body.category, source="user",
                               verified=True, reusable=body.reusable)
    return kb.annotate(await get_db().knowledge_base.find_one({"_id": eid}))


@router.put("/{eid}")
async def update(eid: str, body: KnowledgeUpdate, user=Depends(current_user)):
    col = get_db().knowledge_base
    doc = await col.find_one({"_id": eid, "user_id": user["_id"]})
    if not doc:
        raise HTTPException(404, "Entry not found")
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    if "question" in upd:
        upd["question_norm"] = kb.normalize(upd["question"])
        upd.setdefault("category", kb.categorize(upd["question"]))
    if "answer" in upd:                       # editing = the user vouching for it
        upd.update(verified=True, source="user", confirmed_at=now())
    upd["updated_at"] = now()
    await col.update_one({"_id": eid}, {"$set": upd})
    return kb.annotate(await col.find_one({"_id": eid}))


@router.post("/{eid}/confirm")
async def confirm(eid: str, user=Depends(current_user)):
    col = get_db().knowledge_base
    r = await col.update_one({"_id": eid, "user_id": user["_id"]},
                             {"$set": {"verified": True, "confirmed_at": now(), "updated_at": now()}})
    if not r.matched_count:
        raise HTTPException(404, "Entry not found")
    return kb.annotate(await col.find_one({"_id": eid}))


@router.delete("/{eid}")
async def delete(eid: str, user=Depends(current_user)):
    r = await get_db().knowledge_base.delete_one({"_id": eid, "user_id": user["_id"]})
    if not r.deleted_count:
        raise HTTPException(404, "Entry not found")
    return {"ok": True}
