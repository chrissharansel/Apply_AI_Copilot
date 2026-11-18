"""Collections: users, candidate_profiles, resumes, knowledge_base, applications,
application_questions, agent_sessions, interaction_history, audit_logs.
Documents are plain dicts with string uuid `_id`s."""
import uuid
from datetime import datetime, timezone

from .mongodb import get_db

STATUSES = ["Pending", "In Progress", "Waiting for User Input", "Ready for Review",
            "Submitted", "Failed", "Requires Manual Intervention", "Cancelled"]


def new_id() -> str:
    return uuid.uuid4().hex


def now() -> datetime:
    return datetime.now(timezone.utc)


_HIDDEN = {"password_hash", "embedding", "storage_path"}


def public(doc: dict | None, hide: tuple = ()) -> dict | None:
    if doc is None:
        return None
    d = {k: v for k, v in doc.items() if k not in _HIDDEN and k not in hide}
    if "_id" in d:
        d["id"] = d.pop("_id")
    return d


async def log_audit(user_id: str, action: str, **meta) -> None:
    await get_db().audit_logs.insert_one(
        {"_id": new_id(), "user_id": user_id, "action": action, "meta": meta, "ts": now()})
