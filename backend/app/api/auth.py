from fastapi import APIRouter, Depends, HTTPException
from pymongo.errors import DuplicateKeyError

from ..database.models import log_audit, new_id, now
from ..database.mongodb import get_db
from ..schemas.user import LoginIn, RegisterIn
from ..utils.security import create_token, current_user, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _user(u: dict) -> dict:
    return {"id": u["_id"], "email": u["email"], "name": u["name"]}


@router.post("/register")
async def register(body: RegisterIn):
    uid = new_id()
    try:
        await get_db().users.insert_one({"_id": uid, "email": body.email, "name": body.name.strip(),
                                         "password_hash": hash_password(body.password), "created_at": now()})
    except DuplicateKeyError:
        raise HTTPException(409, "An account with this email already exists.")
    await log_audit(uid, "register")
    return {"token": create_token(uid), "user": {"id": uid, "email": body.email, "name": body.name.strip()}}


@router.post("/login")
async def login(body: LoginIn):
    u = await get_db().users.find_one({"email": body.email.strip().lower()})
    if not u or not verify_password(body.password, u["password_hash"]):
        raise HTTPException(401, "Incorrect email or password.")
    await log_audit(u["_id"], "login")
    return {"token": create_token(u["_id"]), "user": _user(u)}


@router.get("/me")
async def me(user=Depends(current_user)):
    return _user(user)
