"""Unit tests for ChatService.process_message job persistence (Ticket 4.3), get_history filtering (Ticket 8.1), and workspace routing (Ticket 9.3)."""

import io
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.store.memory import InMemoryStore
from pypdf import PdfWriter

from app.agent.constants import FINAL_ANSWER_TOOL_NAME, JOBS_KEY, TEXT_RESPONSE_KEY
from app.services.chat_service import ChatService
from app.services.profile_service import ProfileService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

JOB_A: dict[str, Any] = {
    "id": "abc123def456",
    "title": "Python Developer",
    "company": "Acme Corp",
    "location": "London",
    "salary": "£60,000",
    "description": "Build backend services.",
    "apply_link": "https://example.com/job-1",
}

JOB_B: dict[str, Any] = {
    "id": "def456abc789",
    "title": "ML Engineer",
    "company": "StartupX",
    "location": "Remote",
    "salary": None,
    "description": "Train models.",
    "apply_link": "https://example.com/job-2",
}


def _make_final_answer_message(jobs: list[dict[str, Any]], text: str = "Here are your jobs.") -> AIMessage:
    """Build a fake AIMessage that mimics the agent's final_answer tool call."""
    msg = AIMessage(content="")
    msg.tool_calls = [  # type: ignore[attr-defined]
        {
            "name": FINAL_ANSWER_TOOL_NAME,
            "args": {TEXT_RESPONSE_KEY: text, JOBS_KEY: jobs},
            "id": "tc-001",
        }
    ]
    return msg


def _make_graph_mock(jobs: list[dict[str, Any]]) -> MagicMock:
    """Return a graph mock that yields a single final state containing a final_answer tool call."""
    final_state: dict[str, Any] = {"messages": [_make_final_answer_message(jobs)]}

    async def _astream(*_args: Any, **_kwargs: Any) -> Any:  # type: ignore[override]
        yield final_state

    graph = MagicMock()
    graph.astream = _astream
    return graph


def _make_service(store: InMemoryStore) -> ChatService:
    discovery_graph = _make_graph_mock([JOB_A, JOB_B])
    profile_graph = _make_graph_mock([])
    profile_service = ProfileService(store=store)
    return ChatService(
        discovery_graph=discovery_graph,
        profile_graph=profile_graph,
        store=store,
        profile_service=profile_service,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_message_persists_jobs_to_deck() -> None:
    """After process_message returns jobs, get_pending_jobs returns those jobs."""
    store = InMemoryStore()
    service = _make_service(store)
    profile_service = ProfileService(store=store)

    result = await service.process_message("find me python jobs")

    assert len(result["jobs"]) == 2

    persisted = await profile_service.get_pending_jobs("default_user")
    persisted_ids = {j.id for j in persisted}
    assert JOB_A["id"] in persisted_ids
    assert JOB_B["id"] in persisted_ids


@pytest.mark.asyncio
async def test_process_message_no_duplicates_on_repeated_call() -> None:
    """Calling process_message twice with the same jobs does not create duplicates."""
    store = InMemoryStore()
    service = _make_service(store)
    profile_service = ProfileService(store=store)

    await service.process_message("find me python jobs")
    await service.process_message("find me python jobs again")

    persisted = await profile_service.get_pending_jobs("default_user")
    # Same two jobs keyed by deterministic id — should still be exactly 2
    assert len(persisted) == 2


@pytest.mark.asyncio
async def test_process_message_no_jobs_does_not_call_add_pending() -> None:
    """When the agent returns no jobs, add_pending_jobs is never called."""
    store = InMemoryStore()

    # Graph returns an empty jobs list
    final_state: dict[str, Any] = {"messages": [_make_final_answer_message(jobs=[])]}

    async def _astream(*_args: Any, **_kwargs: Any) -> Any:  # type: ignore[override]
        yield final_state

    graph = MagicMock()
    graph.astream = _astream

    profile_service = ProfileService(store=store)
    with patch.object(profile_service, "add_pending_jobs", new_callable=AsyncMock) as mock_add:
        service = ChatService(
            discovery_graph=graph,
            profile_graph=_make_graph_mock([]),
            store=store,
            profile_service=profile_service,
        )
        await service.process_message("tell me something")
        mock_add.assert_not_called()


@pytest.mark.asyncio
async def test_get_history_filters_system_trigger() -> None:
    """get_history never exposes [SYSTEM TRIGGER] HumanMessages to the frontend."""
    messages = [
        HumanMessage(content="Hi"),
        AIMessage(content="Hello"),
        HumanMessage(content="[SYSTEM TRIGGER] Onboarding is now complete. Begin searching."),
        AIMessage(content="Here are some jobs for you."),
    ]

    graph_state = MagicMock()
    graph_state.values = {"messages": messages}

    graph = MagicMock()
    graph.aget_state = AsyncMock(return_value=graph_state)

    store = InMemoryStore()
    profile_service = MagicMock()
    service = ChatService(
        discovery_graph=graph,
        profile_graph=MagicMock(),
        store=store,
        profile_service=profile_service,
    )

    history = await service.get_history()

    # No turn should have a user_message starting with [SYSTEM TRIGGER]
    for turn in history:
        assert not str(turn["user_message"]).startswith("[SYSTEM TRIGGER]")

    # The "Hi" / "Hello" turn must be present
    assert any(turn["user_message"] == "Hi" for turn in history)


def _make_spy_graph(jobs: list[dict[str, Any]]) -> tuple[MagicMock, list[bool]]:
    """Return a graph mock and a single-element mutable flag.

    flag[0] is set True when astream is called, allowing routing assertions
    without nonlocal boilerplate.
    """
    graph = _make_graph_mock(jobs)
    called: list[bool] = [False]
    original = graph.astream

    async def _spy(*args: Any, **kwargs: Any) -> Any:
        called[0] = True
        async for s in original(*args, **kwargs):
            yield s

    graph.astream = _spy
    return graph, called


def _make_blank_pdf() -> bytes:
    buf = io.BytesIO()
    PdfWriter().write(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_process_message_routes_to_discovery_by_default() -> None:
    """Default workspace routes to the discovery graph."""
    store = InMemoryStore()
    discovery_graph, discovery_called = _make_spy_graph([])
    profile_graph, profile_called = _make_spy_graph([])

    service = ChatService(
        discovery_graph=discovery_graph,
        profile_graph=profile_graph,
        store=store,
        profile_service=ProfileService(store=store),
    )
    await service.process_message("find jobs")

    assert discovery_called[0]
    assert not profile_called[0]


@pytest.mark.asyncio
async def test_process_message_routes_to_profile() -> None:
    """Explicit workspace='profile' routes to the profile graph."""
    store = InMemoryStore()
    discovery_graph, discovery_called = _make_spy_graph([])
    profile_graph, profile_called = _make_spy_graph([])

    service = ChatService(
        discovery_graph=discovery_graph,
        profile_graph=profile_graph,
        store=store,
        profile_service=ProfileService(store=store),
    )
    await service.process_message("update my name", workspace="profile")

    assert profile_called[0]
    assert not discovery_called[0]


@pytest.mark.asyncio
async def test_process_cv_always_uses_profile_graph() -> None:
    """process_cv always uses the profile graph regardless of workspace."""
    store = InMemoryStore()
    discovery_graph, discovery_called = _make_spy_graph([])
    profile_graph, profile_called = _make_spy_graph([])

    service = ChatService(
        discovery_graph=discovery_graph,
        profile_graph=profile_graph,
        store=store,
        profile_service=ProfileService(store=store),
    )
    await service.process_cv(_make_blank_pdf(), filename="cv.pdf")

    assert profile_called[0]
    assert not discovery_called[0]
