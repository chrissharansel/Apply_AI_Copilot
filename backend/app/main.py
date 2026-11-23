
import asyncio
import sys
from contextlib import asynccontextmanager

if sys.platform == "win32":
    # Playwright requires subprocess support on Windows.
    asyncio.set_event_loop_policy(
        asyncio.WindowsProactorEventLoopPolicy()
    )

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .agents.orchestrator import recover_sessions
from .api import (
    agent,
    applications,
    auth,
    knowledge,
    profile,
    resume,
    settings as settings_api,
)
from .config import settings
from .database.mongodb import init_indexes
from .services.browser_service import bm


@asynccontextmanager
async def lifespan(app: FastAPI):
    if len(settings.secret_key) < 16:
        raise RuntimeError(
            "Set SECRET_KEY (16+ random characters) in environment variables"
        )

    await init_indexes()
    await recover_sessions()

    yield

    await bm.shutdown()


app = FastAPI(
    title="ApplyAI",
    version="1.0.0",
    lifespan=lifespan,
)

# Read allowed frontend origins from CORS_ORIGINS
allowed_origins = [
    origin.strip().rstrip("/")
    for origin in settings.cors_origins.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
for router in (
    auth,
    profile,
    resume,
    knowledge,
    applications,
    agent,
    settings_api,
):
    app.include_router(router.router, prefix="/api")


@app.get("/api/ping")
async def ping():
    return {"ok": True}
