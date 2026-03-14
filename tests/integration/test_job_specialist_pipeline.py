# Manual Verification Checklist:
# 1. Start backend: uvicorn app.main:app --reload
# 2. Start frontend: cd frontend && npm run dev
# 3. Upload a CV (any PDF) → verify profile is created
# 4. Send: "Find me senior Python developer jobs in London"
# 5. Check Network tab: POST /api/chat response has jobs[] with full data
#    - description should be AI-generated (~500 chars), not the raw JSearch snippet
#    - full_description should be up to 5,000 chars
# 6. Check server logs: summarize_jobs_parallel and finalize_state log start/complete
# 7. Check server logs: ToolMessage content has job objects WITHOUT full_description
# 8. Send: same query again → verify dedup (seen jobs not in job_payloads)
# 9. Click a job card → verify apply_link works

"""
Integration tests for the full Job Specialist pipeline:
fetch_jobs → dedup → summarize_jobs_parallel → finalize_state.

These tests run through the real 2-node subgraph. Only external I/O
(JSearch API, LLM) is mocked.
"""

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.store.memory import InMemoryStore

from app.agent.constants import DEFAULT_USER_ID
from app.agent.discovery.graph import _run_single_job_search
from app.agent.schemas import JobListing, JobSummary, JobSummaryBatch
from app.services.profile_service import ProfileService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_raw_jsearch_result(job_id: str) -> dict[str, Any]:
    """Simulate a raw dict as returned by jsearch_api_search."""
    return {
        "id": job_id,
        "title": f"Job {job_id}",
        "company": f"Co {job_id}",
        "location": "London, GB",
        "salary": "$80k",
        "description": f"Raw snippet for {job_id}.",
        "full_description": f"Full description for {job_id}. " * 100,
        "apply_link": f"https://{job_id}.com/apply",
    }


def _make_tool_call(query: str = "python developer", tc_id: str = "tc-1") -> dict[str, Any]:
    return {
        "id": tc_id,
        "name": "job_specialist_tool",
        "args": {"query": query, "country": "gb"},
    }


def _mock_summary_llm_ok() -> AsyncMock:
    """Mock LLM that returns valid summaries for any batch."""

    async def _ainvoke(messages: Any) -> JobSummaryBatch:
        jobs = json.loads(messages[-1].content)
        return JobSummaryBatch(summaries=[JobSummary(job_id=j["id"], description=f"AI summary for {j['id']}") for j in jobs])

    return AsyncMock(side_effect=_ainvoke)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_produces_job_payloads_with_full_data() -> None:
    """job_payloads has all jobs with full_description, apply_link, and AI-generated descriptions."""
    raw_jobs = [_make_raw_jsearch_result(str(i)) for i in range(5)]
    store = InMemoryStore()
    service = ProfileService(store)

    with (
        patch("app.agent.job_search.nodes.jsearch_api_search") as mock_jsearch,
        patch("app.agent.job_search.nodes._get_summary_llm") as mock_get_llm,
    ):
        mock_jsearch.invoke.return_value = raw_jobs
        mock_get_llm.return_value.ainvoke = _mock_summary_llm_ok()

        tool_msg, payloads = await _run_single_job_search(_make_tool_call(), service, None, None)

    assert len(payloads) == 5
    for p in payloads:
        assert "full_description" in p
        assert "apply_link" in p
        assert p["description"].startswith("AI summary for")


@pytest.mark.asyncio
async def test_pipeline_tool_message_strips_only_full_description() -> None:
    """tool_message_content has all fields EXCEPT full_description."""
    raw_jobs = [_make_raw_jsearch_result(str(i)) for i in range(5)]
    store = InMemoryStore()
    service = ProfileService(store)

    with (
        patch("app.agent.job_search.nodes.jsearch_api_search") as mock_jsearch,
        patch("app.agent.job_search.nodes._get_summary_llm") as mock_get_llm,
    ):
        mock_jsearch.invoke.return_value = raw_jobs
        mock_get_llm.return_value.ainvoke = _mock_summary_llm_ok()

        tool_msg, _ = await _run_single_job_search(_make_tool_call(), service, None, None)

    content = str(tool_msg.content)
    assert "full_description" not in content
    parsed = json.loads(content)
    assert len(parsed["jobs"]) == 5
    for entry in parsed["jobs"]:
        assert "id" in entry
        assert "title" in entry
        assert "company" in entry
        assert "location" in entry
        assert "salary" in entry
        assert "description" in entry
        assert "apply_link" in entry


@pytest.mark.asyncio
async def test_pipeline_handles_llm_summary_failure_gracefully() -> None:
    """When the LLM fails, all jobs still appear with original raw descriptions."""
    raw_jobs = [_make_raw_jsearch_result(str(i)) for i in range(5)]
    store = InMemoryStore()
    service = ProfileService(store)

    with (
        patch("app.agent.job_search.nodes.jsearch_api_search") as mock_jsearch,
        patch("app.agent.job_search.nodes._get_summary_llm") as mock_get_llm,
    ):
        mock_jsearch.invoke.return_value = raw_jobs
        mock_get_llm.return_value.ainvoke = AsyncMock(side_effect=Exception("LLM down"))

        tool_msg, payloads = await _run_single_job_search(_make_tool_call(), service, None, None)

    # Pipeline does NOT crash — all jobs present with original descriptions
    assert len(payloads) == 5
    for p in payloads:
        assert p["description"].startswith("Raw snippet for")


@pytest.mark.asyncio
async def test_pipeline_handles_llm_timeout() -> None:
    """When the LLM times out, pipeline completes with original descriptions."""
    import asyncio

    raw_jobs = [_make_raw_jsearch_result(str(i)) for i in range(5)]
    store = InMemoryStore()
    service = ProfileService(store)

    async def slow_invoke(*args: Any, **kwargs: Any) -> None:
        await asyncio.sleep(60)

    with (
        patch("app.agent.job_search.nodes.jsearch_api_search") as mock_jsearch,
        patch("app.agent.job_search.nodes._get_summary_llm") as mock_get_llm,
        patch("app.agent.job_search.nodes.SUMMARY_LLM_TIMEOUT", 0.1),
    ):
        mock_jsearch.invoke.return_value = raw_jobs
        mock_get_llm.return_value.ainvoke = slow_invoke

        tool_msg, payloads = await _run_single_job_search(_make_tool_call(), service, None, None)

    # Does NOT hang — all jobs present with original descriptions
    assert len(payloads) == 5
    for p in payloads:
        assert p["description"].startswith("Raw snippet for")


@pytest.mark.asyncio
async def test_pipeline_passes_all_api_results() -> None:
    """15 raw jobs → 15 entries in job_payloads. No cap applied."""
    raw_jobs = [_make_raw_jsearch_result(str(i)) for i in range(15)]
    store = InMemoryStore()
    service = ProfileService(store)

    with (
        patch("app.agent.job_search.nodes.jsearch_api_search") as mock_jsearch,
        patch("app.agent.job_search.nodes._get_summary_llm") as mock_get_llm,
    ):
        mock_jsearch.invoke.return_value = raw_jobs
        mock_get_llm.return_value.ainvoke = _mock_summary_llm_ok()

        tool_msg, payloads = await _run_single_job_search(_make_tool_call(), service, None, None)

    assert len(payloads) == 15


@pytest.mark.asyncio
async def test_pipeline_dedup_excludes_seen_jobs() -> None:
    """Pre-seen jobs are excluded from job_payloads and appear in tool_message 'seen' section."""
    raw_jobs = [_make_raw_jsearch_result(str(i)) for i in range(10)]
    store = InMemoryStore()
    service = ProfileService(store)

    # Pre-seed 3 jobs as seen
    seen_listings = [
        JobListing(
            id=str(i),
            title=f"Job {i}",
            company=f"Co {i}",
            location="London, GB",
            salary="$80k",
            description=f"Raw snippet for {i}.",
            apply_link=f"https://{i}.com/apply",
        )
        for i in range(3)
    ]
    await service.mark_jobs_seen(seen_listings, DEFAULT_USER_ID)

    with (
        patch("app.agent.job_search.nodes.jsearch_api_search") as mock_jsearch,
        patch("app.agent.job_search.nodes._get_summary_llm") as mock_get_llm,
    ):
        mock_jsearch.invoke.return_value = raw_jobs
        mock_get_llm.return_value.ainvoke = _mock_summary_llm_ok()

        tool_msg, payloads = await _run_single_job_search(_make_tool_call(), service, None, None)

    # job_payloads has only fresh jobs (7)
    assert len(payloads) == 7
    payload_ids = {p["id"] for p in payloads}
    assert all(str(i) not in payload_ids for i in range(3))

    # tool_message has seen section
    parsed = json.loads(str(tool_msg.content))
    assert len(parsed["seen"]) == 3
    seen_ids = {s["id"] for s in parsed["seen"]}
    assert seen_ids == {"0", "1", "2"}
