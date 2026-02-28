"""
Unit tests for _format_decisions_summary helper (updated for Ticket 002).
"""

from app.agent.main.nodes import _format_decisions_summary
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
