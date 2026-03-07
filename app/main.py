from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore
from psycopg_pool import AsyncConnectionPool

from app.agent.discovery.graph import get_discovery_graph
from app.agent.profile.graph import get_profile_graph
from app.api.middleware import RequestIdMiddleware
from app.api.routes import router as api_router
from app.core.config import settings
from app.core.database import get_db_connection_uri
from app.core.logging import setup_logging

# Configure structured JSON logging with request correlation
setup_logging()
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Startup
    logger.info("Initializing Application...")

    conn_uri = get_db_connection_uri()
    pool = AsyncConnectionPool(conninfo=conn_uri, max_size=20, kwargs={"autocommit": True})
    await pool.open()

    checkpointer = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
    await checkpointer.setup()
    store = AsyncPostgresStore(pool)  # type: ignore[arg-type]
    await store.setup()
    app.state.pool = pool
    app.state.store = store
    app.state.discovery_graph = get_discovery_graph(checkpointer=checkpointer, store=store)
    app.state.profile_graph = get_profile_graph(checkpointer=checkpointer, store=store)

    logger.info("Application ready.")
    yield

    # Shutdown
    logger.info("Shutting down...")
    await pool.close()


app = FastAPI(title=settings.APP_NAME, debug=settings.DEBUG, lifespan=lifespan)

# CORS: allow the Next.js dev server to call the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestIdMiddleware)

# Include Router (all routes are under /api prefix)
app.include_router(api_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "env": settings.APP_ENV}
