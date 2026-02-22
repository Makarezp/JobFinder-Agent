"""
Unit tests for Ticket 3.2 acceptance criteria:
- _format_decisions_summary helper
"""

from app.agent.main.nodes import _format_decisions_summary
from app.agent.memory_schema import DecisionLog


def test_format_decisions_summary_empty() -> None:
    """Returns the no-history string when the list is empty."""
    assert _format_decisions_summary([]) == "No feedback history yet."


def test_format_decisions_summary_contains_job_titles() -> None:
    """Output includes both job titles."""
    decisions = [
        DecisionLog(
            job_title="Fullstack Dev",
            company="FintechCorp",
            action="pass",
            description="Builds internal tooling for trading desks",
            reason="Legacy technology stack",
            timestamp="2026-02-22T12:00:00+00:00",
        ).model_dump(),
        DecisionLog(
            job_title="Senior Python",
            company="AgencyX",
            action="pass",
            description=None,
            reason="Agency model",
            timestamp="2026-02-22T11:00:00+00:00",
        ).model_dump(),
    ]
    result = _format_decisions_summary(decisions)
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
    assert "Too corporate" in result


def test_format_decisions_summary_omits_description_segment_when_none() -> None:
    """The em-dash description segment is omitted when description is None."""
    decisions = [
        DecisionLog(
            job_title="Dev",
            company="Corp",
            action="pass",
            description=None,
            reason="Old tech",
            timestamp="2026-02-22T12:00:00+00:00",
        ).model_dump(),
    ]
    result = _format_decisions_summary(decisions)
    assert "—" not in result


def test_format_decisions_summary_includes_description_when_present() -> None:
    """The description snippet and em-dash appear when description is provided."""
    decisions = [
        DecisionLog(
            job_title="Dev",
            company="Corp",
            action="pass",
            description="Builds payment APIs in Python",
            reason="Too corporate",
            timestamp="2026-02-22T12:00:00+00:00",
        ).model_dump(),
    ]
    result = _format_decisions_summary(decisions)
    assert "Builds payment APIs in Python" in result
    assert "—" in result


def test_format_decisions_summary_no_description_no_reason() -> None:
    """Entry with neither description nor reason renders cleanly without em-dash or colon."""
    decisions = [
        DecisionLog(
            job_title="Dev",
            company="Corp",
            action="pursue",
            description=None,
            reason=None,
            timestamp="2026-02-22T12:00:00+00:00",
        ).model_dump(),
    ]
    result = _format_decisions_summary(decisions)
    assert "Dev" in result
    assert "Corp" in result
    assert "—" not in result
