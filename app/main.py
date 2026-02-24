import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore
from psycopg_pool import AsyncConnectionPool

from app.agent.graph import get_compiled_graph
from app.api.middleware import RequestIdMiddleware
from app.api.routes import router as api_router
from app.core.config import settings
from app.core.database import get_db_connection_uri
from app.core.logging import setup_logging

# Configure structured JSON logging with request correlation
setup_logging()
logger = logging.getLogger(__name__)


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
    graph = get_compiled_graph(checkpointer=checkpointer, store=store)

    app.state.pool = pool
    app.state.store = store
    app.state.graph = graph

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
