"""
Unit tests for main agent nodes (Ticket 002, Ticket 8.1).
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage as AIMsg
from langchain_core.messages import HumanMessage

from app.agent.constants import DISCOVERY_JOB_SPECIALIST_NODE, MESSAGES_KEY
from app.agent.main.nodes import (
    _format_decisions_summary,
    fetch_profile,
    main_chatbot,
    route_main,
)
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


def _make_store_mock() -> MagicMock:
    """Return a store mock with aget and asearch returning minimal valid values."""
    store = MagicMock()
    store.aget = AsyncMock(return_value=None)
    store.asearch = AsyncMock(return_value=[])
    return store


def _make_config(user_id: str = "test_user") -> dict[str, Any]:
    return {"configurable": {"user_id": user_id}}


# ---------------------------------------------------------------------------
# route_main — presence-based routing
# ---------------------------------------------------------------------------


def test_route_main_detects_job_specialist_at_any_position() -> None:
    """route_main routes to JOB_SPECIALIST_NODE when job_specialist_tool appears at any position."""
    ai_msg = AIMsg(content="")
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
    }

    assert route_main(state) == DISCOVERY_JOB_SPECIALIST_NODE  # type: ignore[arg-type]


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
        "search_attempts": 0,
    }

    await fetch_profile(state, _make_config(user_id), store)  # type: ignore[arg-type]

    store.aget.assert_called_once_with((user_id, "profile"), "data")
    asearch_calls = {call.args[0] for call in store.asearch.call_args_list}
    assert (user_id, "preferences") in asearch_calls
    assert (user_id, "decisions") in asearch_calls


# ---------------------------------------------------------------------------
# main_chatbot — intent logging
# ---------------------------------------------------------------------------


def _make_main_state() -> dict[str, Any]:
    return {
        MESSAGES_KEY: [HumanMessage(content="Find me a job")],
        "user_profile": None,
        "preferences": None,
        "recent_decisions": [],
        "search_attempts": 0,
        "onboarding_complete": True,
        "cv_raw_text": None,
    }


def test_main_chatbot_logs_valid_tool_intent() -> None:
    """main_chatbot logs LLM Intent: Tool Selected for each tool_call."""
    response = AIMsg(content="")
    response.tool_calls = [{"name": "job_specialist_tool", "args": {"query": "python dev"}, "id": "tc-1"}]  # type: ignore[attr-defined, assignment]
    response.invalid_tool_calls = []  # type: ignore[attr-defined, assignment]

    with (
        patch("app.agent.main.nodes.main_llm") as mock_llm,
        patch("app.agent.main.nodes.logger") as mock_logger,
    ):
        mock_llm.invoke.return_value = response
        main_chatbot(_make_main_state())  # type: ignore[arg-type]

        mock_logger.info.assert_any_call(
            "LLM Intent: Tool Selected",
            tool_name="job_specialist_tool",
            tool_args={"query": "python dev"},
        )


def test_main_chatbot_logs_invalid_tool_intent() -> None:
    """main_chatbot logs LLM Intent: Invalid Tool Selected for hallucinated tool calls."""
    response = AIMsg(content="")
    response.tool_calls = []  # type: ignore[attr-defined, assignment]
    response.invalid_tool_calls = [{"name": "fake_tool", "args": None, "error": "unknown tool", "type": "invalid_tool_call", "id": None}]  # type: ignore[attr-defined, assignment]

    with (
        patch("app.agent.main.nodes.main_llm") as mock_llm,
        patch("app.agent.main.nodes.logger") as mock_logger,
    ):
        mock_llm.invoke.return_value = response
        main_chatbot(_make_main_state())  # type: ignore[arg-type]

        mock_logger.warning.assert_any_call(
            "LLM Intent: Invalid Tool Selected",
            tool_name="fake_tool",
            tool_args=None,
            error="unknown tool",
        )
