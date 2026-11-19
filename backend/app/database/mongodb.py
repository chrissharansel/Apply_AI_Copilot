
import certifi
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from ..config import settings

_client: AsyncIOMotorClient | None = None


def get_db() -> AsyncIOMotorDatabase:
    global _client

    if _client is None:
        _client = AsyncIOMotorClient(
            settings.mongodb_uri,
            tz_aware=True,
            tls=True,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=15000,
            connectTimeoutMS=15000,
            socketTimeoutMS=20000,
        )

    return _client[settings.database_name]


async def init_indexes() -> None:
    d = get_db()

    # Verify MongoDB connection before creating indexes
    await d.command("ping")
    print("MongoDB Atlas connected successfully.")

    # User indexes
    await d.users.create_index("email", unique=True)

    # Candidate profile indexes
    await d.candidate_profiles.create_index("user_id", unique=True)

    # Resume indexes
    await d.resumes.create_index([
        ("user_id", 1),
        ("version", -1)
    ])

    # Knowledge base indexes
    await d.knowledge_base.create_index([
        ("user_id", 1),
        ("question_norm", 1)
    ])

    await d.knowledge_base.create_index([
        ("user_id", 1),
        ("category", 1)
    ])

    # Application indexes
    await d.applications.create_index([
        ("user_id", 1),
        ("created_at", -1)
    ])

    await d.application_questions.create_index("application_id")

    # Agent session indexes
    await d.agent_sessions.create_index([
        ("user_id", 1),
        ("created_at", -1)
    ])

    # Interaction history indexes
    await d.interaction_history.create_index([
        ("session_id", 1),
        ("ts", 1)
    ])

    # Audit indexes
    await d.audit_logs.create_index([
        ("user_id", 1),
        ("ts", -1)
    ])

    print("MongoDB indexes initialized successfully.")


async def close_db() -> None:
    global _client

    if _client is not None:
        _client.close()
        _client = None
