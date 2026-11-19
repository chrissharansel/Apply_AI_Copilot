from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from ..config import settings

_client: AsyncIOMotorClient | None = None


def get_db() -> AsyncIOMotorDatabase:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongodb_uri, tz_aware=True)
    return _client[settings.database_name]


async def init_indexes() -> None:
    d = get_db()
    await d.users.create_index("email", unique=True)
    await d.candidate_profiles.create_index("user_id", unique=True)
    await d.resumes.create_index([("user_id", 1), ("version", -1)])
    await d.knowledge_base.create_index([("user_id", 1), ("question_norm", 1)])
    await d.knowledge_base.create_index([("user_id", 1), ("category", 1)])
    await d.applications.create_index([("user_id", 1), ("created_at", -1)])
    await d.application_questions.create_index("application_id")
    await d.agent_sessions.create_index([("user_id", 1), ("created_at", -1)])
    await d.interaction_history.create_index([("session_id", 1), ("ts", 1)])
    await d.audit_logs.create_index([("user_id", 1), ("ts", -1)])
