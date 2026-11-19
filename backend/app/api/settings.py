from fastapi import APIRouter, Depends

from ..database.mongodb import get_db
from ..schemas.settings import UserSettings
from ..utils.security import current_user

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("")
async def get_settings(user=Depends(current_user)):
    return UserSettings(**(user.get("settings") or {})).model_dump()


@router.put("")
async def put_settings(body: UserSettings, user=Depends(current_user)):
    await get_db().users.update_one({"_id": user["_id"]}, {"$set": {"settings": body.model_dump()}})
    return body.model_dump()
