"""
Integration tests for the Search Ledger round-trip (Sprint V2, Ticket 3).

Tests the full cycle: _run_single_job_search writes to ledger,
fetch_profile loads it, reset_discovery_state clears it.
"""

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage
from langgraph.store.memory import InMemoryStore

from app.agent.constants import DEFAULT_USER_ID
from app.agent.discovery.graph import _run_single_job_search
from app.agent.main.nodes import fetch_profile
from app.agent.schemas import JobSpecialistInput, JobSummary, JobSummaryBatch
from app.services.profile_service import ProfileService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _raw_job(job_id: str) -> dict[str, Any]:
    return {
        "id": job_id,
        "title": f"Job {job_id}",
        "company": f"Co {job_id}",
        "location": "London, GB",
        "salary": None,
        "description": f"Desc {job_id}.",
        "full_description": f"Full {job_id}.",
        "apply_link": f"https://example.com/{job_id}",
    }


def _tool_call(query: str = "python developer", tc_id: str = "tc-1") -> dict[str, Any]:
    return {"id": tc_id, "name": "job_specialist_tool", "args": {"query": query, "country": "gb"}}


async def _llm_ok(messages: Any) -> JobSummaryBatch:
    jobs = json.loads(messages[-1].content)
    return JobSummaryBatch(summaries=[JobSummary(job_id=j["id"], description=f"AI summary for {j['id']}") for j in jobs])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ledger_round_trip_through_pipeline() -> None:
    """_run_single_job_search writes to ledger; get_search_ledger reads back correctly."""
    store = InMemoryStore()
    profile_service = ProfileService(store)

    # --- First search: 10 jobs → has_more=True ---
    with (
        patch("app.agent.job_search.nodes.jsearch_api_search") as mock_jsearch,
        patch("app.agent.job_search.nodes._get_summary_llm") as mock_llm,
    ):
        mock_jsearch.invoke.return_value = [_raw_job(str(i)) for i in range(10)]
        mock_llm.return_value.ainvoke = AsyncMock(side_effect=_llm_ok)
        await _run_single_job_search(_tool_call("python developer"), set(), None, None, profile_service)

    ledger = await profile_service.get_search_ledger(DEFAULT_USER_ID)
    assert len(ledger) == 1
    assert ledger[0]["query"] == "python developer"
    assert ledger[0]["results_count"] == 10
    assert ledger[0]["has_more"] is True  # 10 >= FETCH_NUM_PAGES * 10

    # --- Second search: different query ---
    with (
        patch("app.agent.job_search.nodes.jsearch_api_search") as mock_jsearch,
        patch("app.agent.job_search.nodes._get_summary_llm") as mock_llm,
    ):
        mock_jsearch.invoke.return_value = [_raw_job(str(i)) for i in range(5)]
        mock_llm.return_value.ainvoke = AsyncMock(side_effect=_llm_ok)
        await _run_single_job_search(_tool_call("react developer", "tc-2"), set(), None, None, profile_service)

    ledger = await profile_service.get_search_ledger(DEFAULT_USER_ID)
    assert len(ledger) == 2
    # Most recent first
    assert ledger[0]["query"] == "react developer"
    assert ledger[1]["query"] == "python developer"


@pytest.mark.asyncio
async def test_ledger_visible_to_fetch_profile() -> None:
    """Searches logged via ProfileService appear in the fetch_profile state patch."""
    store = InMemoryStore()
    profile_service = ProfileService(store)

    await profile_service.log_search(
        input_data=JobSpecialistInput(query="python dev", country="gb"),
        results_count=10,
        fresh_count=8,
    )
    await profile_service.log_search(
        input_data=JobSpecialistInput(query="react dev", country="gb"),
        results_count=5,
        fresh_count=5,
    )

    state: dict[str, Any] = {
        "messages": [HumanMessage(content="find jobs")],
        "user_profile": None,
        "preferences": None,
        "search_attempts": 0,
    }
    config: dict[str, Any] = {"configurable": {"user_id": DEFAULT_USER_ID}}

    patch_result = await fetch_profile(state, config, store)  # type: ignore[arg-type]

    assert "search_ledger" in patch_result
    assert len(patch_result["search_ledger"]) == 2


@pytest.mark.asyncio
async def test_reset_clears_ledger() -> None:
    """reset_discovery_state wipes the search_ledger namespace."""
    store = InMemoryStore()
    profile_service = ProfileService(store)

    await profile_service.log_search(
        input_data=JobSpecialistInput(query="python dev", country="gb"),
        results_count=5,
        fresh_count=5,
    )
    assert len(await profile_service.get_search_ledger(DEFAULT_USER_ID)) == 1

    await profile_service.reset_discovery_state(DEFAULT_USER_ID)
    assert await profile_service.get_search_ledger(DEFAULT_USER_ID) == []
