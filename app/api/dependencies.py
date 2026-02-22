from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import Depends
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore
from langgraph.store.postgres import AsyncPostgresStore
from psycopg_pool import AsyncConnectionPool

from app.agent.graph import get_compiled_graph
from app.core.database import get_db_connection_uri
from app.services.admin_service import AdminService
from app.services.chat_service import ChatService
from app.services.profile_service import ProfileService

# Singleton-like storage for the pool/checkpointer/store
# In a real production app, you might use app.state or a proper DI container context.
# For simplicity with FastAPI/Uvicorn, we can use global lazy loaders or startup events.
# Here we'll use a cached approach.

_pool: AsyncConnectionPool | None = None
_checkpointer: AsyncPostgresSaver | None = None
_store: AsyncPostgresStore | None = None
_graph: CompiledStateGraph[Any] | None = None


async def get_db_pool() -> AsyncGenerator[AsyncConnectionPool, None]:
    """
    Dependency provides the shared connection pool.
    Initializes it if not present (simple singleton pattern).
    """
    global _pool
    if _pool is None:
        conn_uri = get_db_connection_uri()
        # Ensure autocommit is passed via kwargs for the connection
        _pool = AsyncConnectionPool(conninfo=conn_uri, max_size=20, kwargs={"autocommit": True})
        await _pool.open()

    yield _pool


async def get_checkpointer() -> AsyncGenerator[BaseCheckpointSaver[str], None]:
    """Get the persistent checkpointer."""
    global _checkpointer
    if _checkpointer is None:
        async for pool in get_db_pool():
            _checkpointer = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
            # Ensure it's set up (idempotent usually, or handled in init_db script)
            # await _checkpointer.setup()
            break

    if _checkpointer:
        yield _checkpointer


async def get_store() -> AsyncGenerator[BaseStore, None]:
    """Get the persistent store."""
    global _store
    if _store is None:
        async for pool in get_db_pool():
            _store = AsyncPostgresStore(pool)  # type: ignore[arg-type]
            break

    if _store:
        yield _store


async def get_graph() -> AsyncGenerator[CompiledStateGraph[Any], None]:
    """
    Get the compiled graph with persistent storage injected.
    """
    global _graph
    if _graph is None:
        # We need checkpointer and store to compile
        cp_gen = get_checkpointer()
        store_gen = get_store()

        cp = await cp_gen.__anext__()
        st = await store_gen.__anext__()

        _graph = get_compiled_graph(checkpointer=cp, store=st)

    if _graph:
        yield _graph


async def get_chat_service() -> AsyncGenerator[ChatService, None]:
    """
    Dependency to get ChatService, injected with the persistent graph.
    """
    graph_gen = get_graph()
    store_gen = get_store()

    g = await graph_gen.__anext__()
    s = await store_gen.__anext__()

    service = ChatService(g, s)
    yield service


async def get_admin_service() -> AsyncGenerator[AdminService, None]:
    """
    Dependency to get AdminService.
    Currently stateless, but prepared for future expansion (e.g. logging, auth).
    """
    yield AdminService()


async def get_profile_service(
    store: Annotated[BaseStore, Depends(get_store)],
) -> AsyncGenerator[ProfileService, None]:
    """Dependency to get ProfileService, injected with the shared store."""
    yield ProfileService(store)
