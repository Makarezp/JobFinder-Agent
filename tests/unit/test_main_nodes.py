"""
Unit tests for main agent nodes (Ticket 002, Ticket 8.1).
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage as _AIMessage
from langchain_core.messages import HumanMessage, ToolMessage

from app.agent.constants import JOB_SPECIALIST_NODE, MESSAGES_KEY
from app.agent.main.nodes import _format_decisions_summary, fetch_profile, route_main
from app.agent.memory_schema import DecisionLog


def test_format_decisions_summary_empty_returns_none() -> None:
    """Returns None when the list is empty — caller omits the feedback block entirely."""
    assert _format_decisions_summary([]) is None


def test_format_decisions_summary_contains_job_titles() -> None:
    """Output includes both job titles."""
    decisions = [
        DecisionLog(
            job_title="Fullstack Dev",
            company="FintechCorp",
            action="pass",
            reason="Legacy technology stack",
            timestamp="2026-02-22T12:00:00+00:00",
        ).model_dump(),
        DecisionLog(
            job_title="Senior Python",
            company="AgencyX",
            action="pass",
            reason="Agency model",
            timestamp="2026-02-22T11:00:00+00:00",
        ).model_dump(),
    ]
    result = _format_decisions_summary(decisions)
    assert result is not None
    assert "Fullstack Dev" in result
    assert "Senior Python" in result


def test_format_decisions_summary_contains_reasons() -> None:
    """Output includes the reason strings."""
    decisions = [
        DecisionLog(
            job_title="Dev",
            company="Corp",
            action="pass",
            reason="Too corporate",
            timestamp="2026-02-22T12:00:00+00:00",
        ).model_dump(),
    ]
    result = _format_decisions_summary(decisions)
    assert result is not None
    assert "Too corporate" in result


def test_format_decisions_summary_no_reason() -> None:
    """Entry with no reason renders cleanly with title and company only."""
    decisions = [
        DecisionLog(
            job_title="Dev",
            company="Corp",
            action="pursue",
            reason=None,
            timestamp="2026-02-22T12:00:00+00:00",
        ).model_dump(),
    ]
    result = _format_decisions_summary(decisions)
    assert result is not None
    assert "Dev" in result
    assert "Corp" in result
    assert ":" not in result.split("Corp")[1]  # no colon after company when no reason


# ---------------------------------------------------------------------------
# Ticket 8.1: fetch_profile trigger injection
# ---------------------------------------------------------------------------


def _make_store_mock() -> MagicMock:
    """Return a store mock with aget and asearch returning minimal valid values."""
    store = MagicMock()
    store.aget = AsyncMock(return_value=None)
    store.asearch = AsyncMock(return_value=[])
    return store


def _make_config(user_id: str = "test_user") -> dict[str, Any]:
    return {"configurable": {"user_id": user_id}}


@pytest.mark.asyncio
async def test_fetch_profile_injects_trigger_on_handoff() -> None:
    """fetch_profile appends a [SYSTEM TRIGGER] HumanMessage after onboarding handoff."""
    onboarding_tool_msg = ToolMessage(
        content="Onboarding complete — handing off to job hunting agent.",
        tool_call_id="x",
    )
    state: dict[str, Any] = {
        MESSAGES_KEY: [onboarding_tool_msg],
        "user_profile": None,
        "preferences": None,
        "onboarding_complete": True,
        "cv_raw_text": None,
        "active_agent": "main",
        "search_attempts": 0,
    }

    result = await fetch_profile(state, _make_config(), _make_store_mock())  # type: ignore[arg-type]

    assert "messages" in result
    injected = result["messages"]
    assert len(injected) == 1
    assert isinstance(injected[0], HumanMessage)
    assert str(injected[0].content).startswith("[SYSTEM TRIGGER]")


@pytest.mark.asyncio
async def test_fetch_profile_no_trigger_on_normal_turn() -> None:
    """fetch_profile does NOT inject a trigger when last message is a normal HumanMessage."""
    state: dict[str, Any] = {
        MESSAGES_KEY: [HumanMessage(content="Find me Python jobs")],
        "user_profile": None,
        "preferences": None,
        "onboarding_complete": True,
        "cv_raw_text": None,
        "active_agent": "main",
        "search_attempts": 0,
    }

    result = await fetch_profile(state, _make_config(), _make_store_mock())  # type: ignore[arg-type]

    assert "messages" not in result


# ---------------------------------------------------------------------------
# Ticket 8.2: route_main presence-based routing
# ---------------------------------------------------------------------------


def test_route_main_detects_job_specialist_at_any_position() -> None:
    """route_main routes to JOB_SPECIALIST_NODE when job_specialist_tool appears at any position."""
    ai_msg = _AIMessage(content="")
    ai_msg.tool_calls = [  # type: ignore[attr-defined]
        {"name": "save_preference", "args": {}, "id": "tc-1"},
        {"name": "job_specialist_tool", "args": {"query": "python dev"}, "id": "tc-2"},
    ]
    state: dict[str, Any] = {
        MESSAGES_KEY: [ai_msg],
        "search_attempts": 0,
        "user_profile": None,
        "preferences": None,
        "onboarding_complete": True,
        "cv_raw_text": None,
        "active_agent": "main",
    }

    assert route_main(state) == JOB_SPECIALIST_NODE  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_fetch_profile_reads_store_concurrently() -> None:
    """fetch_profile calls aget and asearch with the correct namespaces."""
    user_id = "test_user"
    store = _make_store_mock()
    state: dict[str, Any] = {
        MESSAGES_KEY: [HumanMessage(content="Find me jobs")],
        "user_profile": None,
        "preferences": None,
        "onboarding_complete": True,
        "cv_raw_text": None,
        "active_agent": "main",
        "search_attempts": 0,
    }

    await fetch_profile(state, _make_config(user_id), store)  # type: ignore[arg-type]

    store.aget.assert_called_once_with((user_id, "profile"), "data")
    asearch_calls = {call.args[0] for call in store.asearch.call_args_list}
    assert (user_id, "preferences") in asearch_calls
    assert (user_id, "decisions") in asearch_calls
