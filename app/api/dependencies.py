"""FastAPI dependency injection providers."""

from app.agent.graph import graph
from app.services.chat_service import ChatService


def get_chat_service() -> ChatService:
    """Provide a ChatService instance wired to the agent graph."""
    return ChatService(graph=graph)
