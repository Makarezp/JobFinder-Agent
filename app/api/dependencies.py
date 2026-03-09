from typing import Annotated, Any

from fastapi import Depends, Request
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore

from app.services.admin_service import AdminService
from app.services.chat_service import ChatService
from app.services.profile_service import ProfileService


def get_store(request: Request) -> BaseStore:  # type: ignore[type-arg]
    return request.app.state.store  # type: ignore[no-any-return]


def get_discovery_graph(request: Request) -> CompiledStateGraph[Any]:  # type: ignore[type-arg]
    return request.app.state.discovery_graph  # type: ignore[no-any-return]


def get_profile_graph(request: Request) -> CompiledStateGraph[Any]:  # type: ignore[type-arg]
    return request.app.state.profile_graph  # type: ignore[no-any-return]


def get_chat_service(
    discovery_graph: Annotated[CompiledStateGraph[Any], Depends(get_discovery_graph)],
    profile_graph: Annotated[CompiledStateGraph[Any], Depends(get_profile_graph)],
    store: Annotated[BaseStore, Depends(get_store)],
) -> ChatService:
    return ChatService(discovery_graph, profile_graph, store, ProfileService(store))


def get_profile_service(
    store: Annotated[BaseStore, Depends(get_store)],
) -> ProfileService:
    return ProfileService(store)


def get_admin_service(
    store: Annotated[BaseStore, Depends(get_store)],
) -> AdminService:
    return AdminService(ProfileService(store))
