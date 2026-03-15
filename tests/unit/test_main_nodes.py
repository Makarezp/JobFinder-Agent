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
    _format_search_ledger,
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
    assert (user_id, "search_ledger") in asearch_calls


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


# ---------------------------------------------------------------------------
# _format_search_ledger
# ---------------------------------------------------------------------------


def test_format_search_ledger_none_returns_none() -> None:
    """Returns None when ledger is empty — caller omits the section entirely."""
    assert _format_search_ledger([]) is None


def test_format_search_ledger_formats_entries() -> None:
    """Entry with has_more=True shows tag; entry with has_more=False does not."""
    ledger = [
        {
            "query": "Python Developer in London",
            "country": "gb",
            "page": 1,
            "results_count": 10,
            "fresh_count": 7,
            "has_more": True,
            "searched_at": "2026-03-15T14:30:00+00:00",
        },
        {
            "query": "React Developer in London",
            "country": "gb",
            "page": 1,
            "results_count": 5,
            "fresh_count": 5,
            "has_more": False,
            "searched_at": "2026-03-15T14:25:00+00:00",
        },
    ]
    result = _format_search_ledger(ledger)
    assert result is not None
    assert "[MORE PAGES AVAILABLE]" in result
    # The second entry must NOT have the tag
    lines = result.splitlines()
    assert "[MORE PAGES AVAILABLE]" in lines[0]
    assert "[MORE PAGES AVAILABLE]" not in lines[1]


def test_format_search_ledger_includes_all_fields() -> None:
    """Output contains query, country, page, results_count, fresh_count, and searched_at."""
    entry: dict[str, Any] = {
        "query": "Staff Engineer",
        "country": "us",
        "page": 2,
        "results_count": 8,
        "fresh_count": 3,
        "has_more": False,
        "searched_at": "2026-03-15T10:00:00+00:00",
    }
    result = _format_search_ledger([entry])
    assert result is not None
    assert "Staff Engineer" in result
    assert "us" in result
    assert "page=2" in result
    assert "8" in result  # results_count
    assert "3" in result  # fresh_count
    assert "2026-03-15T10:00:00+00:00" in result


# ---------------------------------------------------------------------------
# fetch_profile — ledger loading
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_profile_loads_search_ledger() -> None:
    """fetch_profile fetches ledger entries and returns them sorted by searched_at descending."""
    user_id = "test_user"
    store = _make_store_mock()

    older = MagicMock()
    older.value = {
        "query": "Python Dev",
        "country": "gb",
        "page": 1,
        "results_count": 5,
        "fresh_count": 5,
        "has_more": False,
        "searched_at": "2026-03-15T10:00:00+00:00",
    }
    newer = MagicMock()
    newer.value = {
        "query": "React Dev",
        "country": "gb",
        "page": 1,
        "results_count": 10,
        "fresh_count": 8,
        "has_more": True,
        "searched_at": "2026-03-15T12:00:00+00:00",
    }

    async def asearch_side_effect(namespace: Any, **kwargs: Any) -> list[Any]:
        if namespace[1] == "search_ledger":
            return [older, newer]
        return []

    store.asearch = AsyncMock(side_effect=asearch_side_effect)

    state: dict[str, Any] = {
        "messages": [HumanMessage(content="Find me jobs")],
        "user_profile": None,
        "preferences": None,
        "onboarding_complete": True,
        "cv_raw_text": None,
        "search_attempts": 0,
    }

    patch_result = await fetch_profile(state, _make_config(user_id), store)  # type: ignore[arg-type]

    assert "search_ledger" in patch_result
    ledger = patch_result["search_ledger"]
    assert len(ledger) == 2
    # Most recent first
    assert ledger[0]["searched_at"] == "2026-03-15T12:00:00+00:00"
    assert ledger[1]["searched_at"] == "2026-03-15T10:00:00+00:00"


# ---------------------------------------------------------------------------
# main_chatbot — search history prompt injection
# ---------------------------------------------------------------------------


def _make_main_state_with_ledger(ledger: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        MESSAGES_KEY: [HumanMessage(content="Find me a job")],
        "user_profile": None,
        "preferences": None,
        "recent_decisions": [],
        "search_ledger": ledger,
        "search_attempts": 0,
        "onboarding_complete": True,
        "cv_raw_text": None,
    }


def test_main_chatbot_includes_search_history_in_prompt() -> None:
    """System message contains SEARCH HISTORY when ledger is non-empty."""
    ledger_entry = {
        "query": "Python Developer in London",
        "country": "gb",
        "page": 1,
        "results_count": 10,
        "fresh_count": 7,
        "has_more": True,
        "searched_at": "2026-03-15T14:30:00+00:00",
    }
    response = AIMsg(content="done")
    response.tool_calls = []  # type: ignore[attr-defined, assignment]
    response.invalid_tool_calls = []  # type: ignore[attr-defined, assignment]

    captured_messages: list[Any] = []

    def fake_invoke(messages: Any) -> AIMsg:
        captured_messages.extend(messages)
        return response

    with patch("app.agent.main.nodes.main_llm") as mock_llm:
        mock_llm.invoke.side_effect = fake_invoke
        main_chatbot(_make_main_state_with_ledger([ledger_entry]))  # type: ignore[arg-type]

    system_content = captured_messages[0].content
    assert "SEARCH HISTORY" in system_content
    assert "Python Developer in London" in system_content


def test_main_chatbot_omits_search_history_when_empty() -> None:
    """System message does NOT contain SEARCH HISTORY when ledger is empty."""
    response = AIMsg(content="done")
    response.tool_calls = []  # type: ignore[attr-defined, assignment]
    response.invalid_tool_calls = []  # type: ignore[attr-defined, assignment]

    captured_messages: list[Any] = []

    def fake_invoke(messages: Any) -> AIMsg:
        captured_messages.extend(messages)
        return response

    with patch("app.agent.main.nodes.main_llm") as mock_llm:
        mock_llm.invoke.side_effect = fake_invoke
        main_chatbot(_make_main_state_with_ledger([]))  # type: ignore[arg-type]

    system_content = captured_messages[0].content
    assert "SEARCH HISTORY" not in system_content


def test_system_prompt_template_accepts_search_history_block() -> None:
    """Smoke test: SYSTEM_PROMPT.format() with search_history_block does not raise KeyError."""
    from app.agent.main.prompts import SYSTEM_PROMPT

    # Should not raise
    result = SYSTEM_PROMPT.format(
        name="Alice",
        role="Engineer",
        profile_summary="10 years Python",
        preferences_summary="Remote only",
        feedback_block="",
        search_history_block="",
        max_search_attempts=5,
    )
    assert "Alice" in result
