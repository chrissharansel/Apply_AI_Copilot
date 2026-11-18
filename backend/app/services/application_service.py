from ..database.models import new_id, now
from ..database.mongodb import get_db


async def create_application(user_id: str, url: str, session_id: str, resume: dict) -> str:
    aid = new_id()
    await get_db().applications.insert_one({
        "_id": aid, "user_id": user_id, "session_id": session_id, "url": url, "company": "", "job_title": "",
        "resume_id": resume["_id"], "resume_version": resume["version"], "resume_filename": resume["filename"],
        "status": "Pending", "confirmation": None, "errors": [], "applied_at": None,
        "created_at": now(), "updated_at": now()})
    return aid


async def update(aid: str, **fields) -> None:
    fields["updated_at"] = now()
    await get_db().applications.update_one({"_id": aid}, {"$set": fields})


async def set_status(aid: str, status: str, error: str | None = None, **extra) -> None:
    upd = {"status": status, **extra}
    ops: dict = {"$set": {**upd, "updated_at": now()}}
    if error:
        ops["$push"] = {"errors": {"at": now(), "message": error}}
    await get_db().applications.update_one({"_id": aid}, ops)


async def save_questions(aid: str, user_id: str, items: list[dict]) -> None:
    col = get_db().application_questions
    await col.delete_many({"application_id": aid})
    if items:
        await col.insert_many([{
            "_id": new_id(), "application_id": aid, "user_id": user_id, "label": i["label"], "kind": i["kind"],
            "category": i.get("category"), "answer": i.get("value"), "source": i.get("source"),
            "confidence": i.get("confidence"), "flags": i.get("flags", []), "status": i.get("status"),
            "required": i.get("required", False), "created_at": now()} for i in items])


async def stats(user_id: str) -> dict:
    col = get_db().applications
    c = lambda q: col.count_documents({"user_id": user_id, **q})
    return {"total": await c({}), "submitted": await c({"status": "Submitted"}),
            "in_progress": await c({"status": {"$in": ["Pending", "In Progress", "Ready for Review"]}}),
            "waiting": await c({"status": "Waiting for User Input"}),
            "failed": await c({"status": {"$in": ["Failed", "Requires Manual Intervention"]}})}
