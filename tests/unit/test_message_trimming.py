"""
Unit tests for the token-trimming

Tests three facts about our custom code (NOT about trim_messages itself,
which is a LangChain built-in with its own test suite):

1. When message history is under the 160k char cap, ALL messages reach the LLM.
2. When message history exceeds the cap, only the trimmed subset reaches the LLM.
3. The structured log line fires if and only if trimming actually activated.
"""

from typing import Any
from unittest.mock import patch

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.agent.constants import MESSAGES_KEY


def _make_state(messages: list[BaseMessage]) -> dict[str, Any]:
    """Build a minimal AgentState dict for main_chatbot."""
    return {
        MESSAGES_KEY: messages,
        "user_profile": {"name": "Jane", "role": "Engineer", "cv_summary": None},
        "preferences": {},
        "recent_decisions": [],
    }


def _make_fake_ai_response() -> AIMessage:
    return AIMessage(content="Here are some jobs.")


# ---------------------------------------------------------------------------
# Helpers: message factories
# ---------------------------------------------------------------------------


def _small_messages() -> list[BaseMessage]:
    """A handful of messages well under 160k chars total."""
    return [
        HumanMessage(content="Find me a remote Python job"),
        AIMessage(content="Sure, searching now..."),
        HumanMessage(content="Any results?"),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMessageTrimming:
    """main_chatbot trims history before LLM invocation."""

    def test_under_cap_all_messages_reach_llm(self) -> None:
        """When under 160k chars, every message is forwarded to the LLM unchanged."""
        messages = _small_messages()
        state = _make_state(messages)

        with patch("app.agent.main.nodes.main_llm") as mock_llm:
            mock_llm.invoke.return_value = _make_fake_ai_response()

            from app.agent.main.nodes import main_chatbot

            main_chatbot(state)

        call_args = mock_llm.invoke.call_args[0][0]  # positional arg: all_messages
        # system prompt is prepended, so history starts at index 1
        passed_history = call_args[1:]
        assert len(passed_history) == len(messages)

    def test_over_cap_trimmed_messages_reach_llm(self) -> None:
        """When trim_messages drops messages, the LLM receives the shorter list — not the full history."""
        all_messages = _small_messages()  # 3 messages
        trimmed = all_messages[-1:]  # simulate trim: only keep last 1
        state = _make_state(all_messages)

        with (
            patch("app.agent.main.nodes.main_llm") as mock_llm,
            patch("app.agent.main.nodes.trim_messages", return_value=trimmed),
        ):
            mock_llm.invoke.return_value = _make_fake_ai_response()

            from app.agent.main.nodes import main_chatbot

            main_chatbot(state)

        call_args = mock_llm.invoke.call_args[0][0]  # positional arg: all_messages
        passed_history = call_args[1:]  # skip leading SystemMessage
        assert len(passed_history) == 1, f"LLM should receive only the trimmed 1 message, got {len(passed_history)}"

    def test_state_messages_not_mutated(self) -> None:
        """Trimming must NOT mutate state[MESSAGES_KEY] — the checkpointer keeps full history."""
        messages = _small_messages()
        original_len = len(messages)
        state = _make_state(messages)

        with patch("app.agent.main.nodes.main_llm") as mock_llm:
            mock_llm.invoke.return_value = _make_fake_ai_response()

            from app.agent.main.nodes import main_chatbot

            main_chatbot(state)

        assert len(state[MESSAGES_KEY]) == original_len, "state[MESSAGES_KEY] must remain unmodified after trimming"

    def test_log_fires_when_trimming_activates(self) -> None:
        """logger.info fires with 'Messages trimmed' when trim_messages returns fewer messages."""
        all_messages = _small_messages()  # 3 messages
        trimmed = all_messages[-1:]  # simulate trim: only 1 survives
        state = _make_state(all_messages)

        with (
            patch("app.agent.main.nodes.main_llm") as mock_llm,
            patch("app.agent.main.nodes.trim_messages", return_value=trimmed),
            patch("app.agent.main.nodes.logger") as mock_logger,
        ):
            mock_llm.invoke.return_value = _make_fake_ai_response()

            from app.agent.main.nodes import main_chatbot

            main_chatbot(state)

        log_calls = [str(call) for call in mock_logger.info.call_args_list]
        trim_logs = [c for c in log_calls if "Messages trimmed" in c]
        assert trim_logs, "Expected a 'Messages trimmed' log line when trim_messages returns fewer messages"

    def test_log_does_not_fire_when_under_cap(self) -> None:
        """logger.info is NOT called with 'Messages trimmed' when history is under cap."""
        messages = _small_messages()
        state = _make_state(messages)

        with (
            patch("app.agent.main.nodes.main_llm") as mock_llm,
            patch("app.agent.main.nodes.logger") as mock_logger,
        ):
            mock_llm.invoke.return_value = _make_fake_ai_response()

            from app.agent.main.nodes import main_chatbot

            main_chatbot(state)

        log_calls = [str(call) for call in mock_logger.info.call_args_list]
        trim_logs = [c for c in log_calls if "Messages trimmed" in c]
        assert not trim_logs, "No trimming log should fire when history is under the cap"
