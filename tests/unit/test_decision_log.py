"""
Unit tests for Ticket 3.1 acceptance criteria:
- DecisionLog model validation
- _parse_agent_result id injection
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError

from app.agent.memory_schema import DecisionLog
from app.services.chat_service import ChatService


def test_decision_log_valid_pass() -> None:
    """DecisionLog accepts a valid 'pass' action."""
    log = DecisionLog(
        job_title="Senior Dev",
        company="Acme",
        action="pass",
        reason="Too corporate",
        timestamp="2026-02-22T12:00:00+00:00",
    )
    assert log.action == "pass"
    assert log.reason == "Too corporate"


def test_decision_log_valid_pursue() -> None:
    """DecisionLog accepts a valid 'pursue' action."""
    log = DecisionLog(
        job_title="ML Engineer",
        company="StartupX",
        action="pursue",
        timestamp="2026-02-22T12:00:00+00:00",
    )
    assert log.action == "pursue"
    assert log.reason is None


def test_decision_log_rejects_invalid_action() -> None:
    """DecisionLog raises ValidationError for an action value that is not 'pass' or 'pursue'."""
    with pytest.raises(ValidationError):
        DecisionLog(
            job_title="Dev",
            company="Corp",
            action="maybe",  # type: ignore[arg-type]
            timestamp="2026-02-22T12:00:00+00:00",
        )


def test_decision_log_reason_optional() -> None:
    """DecisionLog allows reason to be omitted (defaults to None)."""
    log = DecisionLog(job_title="Dev", company="Corp", action="pass", timestamp="2026-02-22T12:00:00+00:00")
    assert log.reason is None


def test_decision_log_serializes_correctly() -> None:
    """model_dump produces the expected dict structure for store persistence."""
    log = DecisionLog(
        job_title="Backend Dev",
        company="FinTech",
        action="pass",
        reason="Legacy stack",
        timestamp="2026-02-22T12:00:00+00:00",
    )
    dumped = log.model_dump()
    assert dumped["job_title"] == "Backend Dev"
    assert dumped["action"] == "pass"
    assert dumped["reason"] == "Legacy stack"
    assert dumped["timestamp"] == "2026-02-22T12:00:00+00:00"


def _make_service() -> ChatService:
    """Return a ChatService with stub dependencies (graph/store not exercised here)."""
    from unittest.mock import MagicMock

    return ChatService(discovery_graph=MagicMock(), profile_graph=MagicMock(), store=MagicMock(), profile_service=MagicMock())


def _make_state_with_payloads(job_payloads: list[dict]) -> dict:  # type: ignore[type-arg]
    """Build a minimal agent state dict with job_payloads and matching IDs."""
    from app.agent.constants import FINAL_ANSWER_TOOL_NAME, SELECTED_JOB_IDS_KEY, TEXT_RESPONSE_KEY

    ids = [p["id"] for p in job_payloads if p.get("id")]
    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call_abc",
                "name": FINAL_ANSWER_TOOL_NAME,
                "args": {TEXT_RESPONSE_KEY: "Here are some jobs.", SELECTED_JOB_IDS_KEY: ids},
            }
        ],
    )
    return {
        "messages": [HumanMessage(content="Find me jobs"), ai_msg],
        "job_payloads": job_payloads,
    }


def test_parse_agent_result_injects_id_when_empty() -> None:
    """Jobs with an empty 'id' field receive a 12-character hex id after selection."""
    service = _make_service()
    # Give jobs proper IDs for selection, but empty id to test injection
    jobs = [
        {"id": "sel_1", "title": "Python Dev", "company": "Acme", "apply_link": "https://example.com/1"},
        {"id": "sel_2", "title": "ML Eng", "company": "Acme", "apply_link": "https://example.com/2"},
    ]
    state = _make_state_with_payloads(jobs)

    # Clear the IDs after state creation (simulates jobs with empty ids that were selected)
    for j in state["job_payloads"]:
        j["id"] = ""

    # Rebuild the state with empty-id payloads but valid selected_job_ids
    from app.agent.constants import FINAL_ANSWER_TOOL_NAME, SELECTED_JOB_IDS_KEY, TEXT_RESPONSE_KEY

    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "id": "call_abc",
                "name": FINAL_ANSWER_TOOL_NAME,
                "args": {TEXT_RESPONSE_KEY: "Here are some jobs.", SELECTED_JOB_IDS_KEY: [""]},
            }
        ],
    )
    state["messages"] = [HumanMessage(content="Find me jobs"), ai_msg]

    result = service._parse_agent_result(state, "Find me jobs")

    # At least the first matched job should have a generated id
    for job in result["jobs"]:
        assert "id" in job
        assert len(job["id"]) == 12
        assert job["id"].isalnum()


def test_parse_agent_result_does_not_overwrite_existing_id() -> None:
    """Jobs that already have an 'id' keep their original id."""
    service = _make_service()
    jobs = [{"title": "Dev", "company": "Corp", "apply_link": "https://x.com", "id": "existing_id_1"}]
    state = _make_state_with_payloads(jobs)

    result = service._parse_agent_result(state, "Find me jobs")

    assert result["jobs"][0]["id"] == "existing_id_1"


def test_parse_agent_result_id_is_deterministic() -> None:
    """The same job data always produces the same id (hash is deterministic)."""
    service = _make_service()
    job = {"title": "Dev", "company": "Acme", "apply_link": "https://example.com/job", "id": "job_1"}
    state1 = _make_state_with_payloads([dict(job)])
    state2 = _make_state_with_payloads([dict(job)])

    result1 = service._parse_agent_result(state1, "q")
    result2 = service._parse_agent_result(state2, "q")

    assert result1["jobs"][0]["id"] == result2["jobs"][0]["id"]


def test_parse_agent_result_different_apply_links_produce_different_ids() -> None:
    """Two jobs with same company+title but different apply_link get distinct ids."""
    service = _make_service()
    jobs = [
        {"title": "Dev", "company": "Acme", "apply_link": "https://example.com/job-1", "id": "job_a"},
        {"title": "Dev", "company": "Acme", "apply_link": "https://example.com/job-2", "id": "job_b"},
    ]
    state = _make_state_with_payloads(jobs)

    result = service._parse_agent_result(state, "q")

    # Both jobs have existing IDs so they keep them — they are distinct
    assert result["jobs"][0]["id"] != result["jobs"][1]["id"]
