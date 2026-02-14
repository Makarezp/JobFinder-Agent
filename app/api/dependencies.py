from collections.abc import Generator
from typing import Any

from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore

from app.agent.graph import graph
from app.agent.graph import store as _store
from app.services.chat_service import ChatService


def get_graph() -> Generator[CompiledStateGraph[Any], None, None]:
    """
    Dependency to get the compiled LangGraph instance.
    """
    yield graph


def get_store() -> Generator[BaseStore, None, None]:
    """
    Dependency to get the shared InMemoryStore instance.
    """
    yield _store


def get_chat_service() -> Generator[ChatService, None, None]:
    """
    Dependency to get an instance of ChatService with the graph injected.
    """
    # Create service instance (stateless or per-request if needed)
    # Since ChatService just holds the graph, it can be lightweight.
    service = ChatService(graph, _store)
    yield service
