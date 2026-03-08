"""
Unit tests for Ticket 005: seen-job deduplication in call_job_specialist.

Tests five concrete facts about our custom code:

1. fresh/seen split is correct when some IDs are pre-seen (mixed case)
2. All jobs appear under "fresh" on first search (empty store)
3. All jobs appear under "seen" when every ID was previously seen
4. mark_jobs_seen is called with fresh-only jobs (guards the fetch→split→mark ordering)
5. Seen-payload entries contain only the 4 identity fields — no description, salary, apply_link
"""

import json
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.store.memory import InMemoryStore

from app.agent.constants import DEFAULT_USER_ID
from app.agent.discovery.graph import call_job_specialist
from app.agent.discovery.state import DiscoveryAgentState
from app.agent.schemas import JobListing
from app.services.profile_service import ProfileService

TEST_USER = DEFAULT_USER_ID


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_job(job_id: str, title: str = "Engineer") -> JobListing:
    return JobListing(
        id=job_id,
        title=title,
        company="Acme Corp",
        location="London",
        salary="£80,000",
        description="Build stuff.",
        apply_link=f"https://example.com/{job_id}",
    )


def _make_state(tool_call_id: str = "tc-1") -> DiscoveryAgentState:
    """Minimal DiscoveryAgentState that triggers call_job_specialist to proceed."""
    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "id": tool_call_id,
                "name": "job_specialist_tool",
                "args": {
                    "query": "python engineer london",
                    "country": "gb",
                    "date_posted": "all",
                    "employment_types": None,
                    "remote_only": False,
                    "page": 1,
                },
            }
        ],
    )
    return cast(
        DiscoveryAgentState,
        {
            "messages": [ai_msg],
            "search_attempts": 0,
        },
    )


def _parse_tool_message(result: dict[str, Any]) -> dict[str, Any]:
    """Extract and parse the JSON payload from the ToolMessage in result."""
    messages = result["messages"]
    assert len(messages) == 1
    assert isinstance(messages[0], ToolMessage)
    return cast(dict[str, Any], json.loads(messages[0].content))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fresh_seen_split_mixed() -> None:
    """
    Given a store with pre-existing seen job ID "abc", and search results ["abc", "new1"],
    verify "new1" appears under fresh (with full data) and "abc" under seen (identity only).
    """
    store = InMemoryStore()
    service = ProfileService(store)
    job_abc = _make_job("abc", "Old Job")
    job_new1 = _make_job("new1", "New Python Role")

    # Pre-seed "abc" as already seen
    await service.mark_jobs_seen([job_abc], TEST_USER)

    state = _make_state()

    with patch("app.agent.discovery.graph.job_search_graph") as mock_graph:
        mock_graph.ainvoke = AsyncMock(return_value={"search_results": [job_abc, job_new1]})
        result = await call_job_specialist(state, profile_service=service)

    payload = _parse_tool_message(result)
    fresh_ids = [j["id"] for j in payload["fresh"]]
    seen_ids = [j["id"] for j in payload["seen"]]

    assert "new1" in fresh_ids
    assert "abc" not in fresh_ids
    assert "abc" in seen_ids
    assert "new1" not in seen_ids


@pytest.mark.asyncio
async def test_first_search_all_fresh() -> None:
    """Given an empty store, all search results appear under 'fresh' and 'seen' is empty."""
    store = InMemoryStore()
    service = ProfileService(store)
    jobs = [_make_job("j1"), _make_job("j2"), _make_job("j3")]
    state = _make_state()

    with patch("app.agent.discovery.graph.job_search_graph") as mock_graph:
        mock_graph.ainvoke = AsyncMock(return_value={"search_results": jobs})
        result = await call_job_specialist(state, profile_service=service)

    payload = _parse_tool_message(result)
    assert len(payload["fresh"]) == 3
    assert payload["seen"] == []


@pytest.mark.asyncio
async def test_all_results_already_seen() -> None:
    """When every returned job ID is already seen, 'fresh' is empty and all appear under 'seen'."""
    store = InMemoryStore()
    service = ProfileService(store)
    jobs = [_make_job("j1"), _make_job("j2")]

    # Pre-seed all jobs as seen
    await service.mark_jobs_seen(jobs, TEST_USER)

    state = _make_state()

    with patch("app.agent.discovery.graph.job_search_graph") as mock_graph:
        mock_graph.ainvoke = AsyncMock(return_value={"search_results": jobs})
        result = await call_job_specialist(state, profile_service=service)

    payload = _parse_tool_message(result)
    assert payload["fresh"] == []
    seen_ids = {j["id"] for j in payload["seen"]}
    assert seen_ids == {"j1", "j2"}


@pytest.mark.asyncio
async def test_mark_jobs_seen_called_with_fresh_only() -> None:
    """
    mark_jobs_seen must be called with only the fresh jobs.
    Guards the critical ordering: fetch seen IDs → split → mark fresh.
    """
    store = InMemoryStore()
    service = ProfileService(store)

    job_old = _make_job("old")
    job_new = _make_job("new")

    # Pre-seed "old" as seen
    await service.mark_jobs_seen([job_old], TEST_USER)

    state = _make_state()

    # Spy on mark_jobs_seen to capture what it was called with
    original_mark = service.mark_jobs_seen
    captured: list[list[JobListing]] = []

    async def spy_mark(jobs: list[JobListing], user_id: str = TEST_USER) -> None:
        captured.append(list(jobs))
        await original_mark(jobs, user_id)

    service.mark_jobs_seen = spy_mark  # type: ignore[method-assign]

    with patch("app.agent.discovery.graph.job_search_graph") as mock_graph:
        mock_graph.ainvoke = AsyncMock(return_value={"search_results": [job_old, job_new]})
        from app.agent.discovery.graph import call_job_specialist

        await call_job_specialist(state, profile_service=service)

    assert len(captured) == 1, "mark_jobs_seen should be called exactly once"
    marked_ids = {j.id for j in captured[0]}
    assert marked_ids == {"new"}, "Only fresh job 'new' should be marked — not 'old'"


@pytest.mark.asyncio
async def test_seen_payload_has_no_description() -> None:
    """Seen-payload entries contain only id, title, company, location — no description, salary, apply_link."""
    store = InMemoryStore()
    service = ProfileService(store)
    job = _make_job("j1", "Senior Engineer")

    # Pre-seed as seen
    await service.mark_jobs_seen([job], TEST_USER)

    state = _make_state()

    with patch("app.agent.discovery.graph.job_search_graph") as mock_graph:
        mock_graph.ainvoke = AsyncMock(return_value={"search_results": [job]})
        result = await call_job_specialist(state, profile_service=service)

    payload = _parse_tool_message(result)
    assert len(payload["seen"]) == 1
    seen_entry = payload["seen"][0]

    allowed_keys = {"id", "title", "company", "location"}
    assert set(seen_entry.keys()) == allowed_keys, f"Seen entry must contain only {allowed_keys}, got {set(seen_entry.keys())}"
