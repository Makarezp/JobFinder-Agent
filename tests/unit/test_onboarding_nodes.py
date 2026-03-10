"""
Unit tests for onboarding agent nodes — intent logging (Ticket 10.2).
"""

from typing import Any
from unittest.mock import patch

from langchain_core.messages import AIMessage as AIMsg
from langchain_core.messages import HumanMessage

from app.agent.constants import MESSAGES_KEY
from app.agent.onboarding.nodes import onboarding_chatbot


def _make_onboarding_state() -> dict[str, Any]:
    return {
        MESSAGES_KEY: [HumanMessage(content="Hello")],
        "onboarding_complete": False,
        "cv_raw_text": None,
    }


def test_onboarding_chatbot_logs_valid_tool_intent() -> None:
    """onboarding_chatbot logs LLM Intent: Tool Selected for each tool_call."""
    response = AIMsg(content="")
    response.tool_calls = [{"name": "update_my_profile", "args": {"name": "Alice"}, "id": "tc-1"}]  # type: ignore[attr-defined, assignment]
    response.invalid_tool_calls = []  # type: ignore[attr-defined, assignment]

    with (
        patch("app.agent.onboarding.nodes.onboarding_llm") as mock_llm,
        patch("app.agent.onboarding.nodes.logger") as mock_logger,
    ):
        mock_llm.invoke.return_value = response
        onboarding_chatbot(_make_onboarding_state())  # type: ignore[arg-type]

        mock_logger.info.assert_any_call(
            "LLM Intent: Tool Selected",
            tool_name="update_my_profile",
            tool_args={"name": "Alice"},
        )


def test_onboarding_chatbot_logs_invalid_tool_intent() -> None:
    """onboarding_chatbot logs LLM Intent: Invalid Tool Selected for hallucinated tool calls."""
    response = AIMsg(content="")
    response.tool_calls = []  # type: ignore[attr-defined, assignment]
    response.invalid_tool_calls = [{"name": "ghost_tool", "args": None, "error": "schema mismatch", "type": "invalid_tool_call", "id": None}]  # type: ignore[attr-defined, assignment]

    with (
        patch("app.agent.onboarding.nodes.onboarding_llm") as mock_llm,
        patch("app.agent.onboarding.nodes.logger") as mock_logger,
    ):
        mock_llm.invoke.return_value = response
        onboarding_chatbot(_make_onboarding_state())  # type: ignore[arg-type]

        mock_logger.warning.assert_any_call(
            "LLM Intent: Invalid Tool Selected",
            tool_name="ghost_tool",
            tool_args=None,
            error="schema mismatch",
        )
