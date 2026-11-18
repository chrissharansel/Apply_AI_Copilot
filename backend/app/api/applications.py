from fastapi import APIRouter, Depends, HTTPException

from ..database.models import public
from ..database.mongodb import get_db
from ..services import application_service
from ..utils.security import current_user

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("")
async def list_apps(user=Depends(current_user)):
    docs = await get_db().applications.find({"user_id": user["_id"]}).sort("created_at", -1).to_list(500)
    return [public(d) for d in docs]


@router.get("/stats")
async def stats(user=Depends(current_user)):
    return await application_service.stats(user["_id"])


@router.get("/{aid}")
async def detail(aid: str, user=Depends(current_user)):
    db = get_db()
    a = await db.applications.find_one({"_id": aid, "user_id": user["_id"]})
    if not a:
        raise HTTPException(404, "Application not found")
    qs = await db.application_questions.find({"application_id": aid}).to_list(500)
    return {**public(a), "questions": [public(q) for q in qs]}
