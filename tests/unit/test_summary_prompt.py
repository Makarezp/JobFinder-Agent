from langchain_core.prompts import ChatPromptTemplate

from app.agent.job_search.prompts import (
    SUMMARY_PROMPT,
    format_preferences_for_summary,
    format_profile_for_summary,
)


class TestFormatProfileForSummary:
    def test_none_returns_fallback(self) -> None:
        assert format_profile_for_summary(None) == "No profile information available."

    def test_empty_dict_returns_fallback(self) -> None:
        assert format_profile_for_summary({}) == "No profile information available."

    def test_includes_all_fields(self) -> None:
        result = format_profile_for_summary({"name": "Alice", "role": "Backend Engineer", "cv_summary": "5 years Python"})
        assert "Alice" in result
        assert "Backend Engineer" in result
        assert "5 years Python" in result


class TestFormatPreferencesForSummary:
    def test_none_returns_fallback(self) -> None:
        assert format_preferences_for_summary(None) == "No preferences set."

    def test_empty_dict_returns_fallback(self) -> None:
        assert format_preferences_for_summary({}) == "No preferences set."

    def test_formats_want_and_avoid(self) -> None:
        result = format_preferences_for_summary(
            {
                "remote": {"key": "remote", "label": "Remote only", "sentiment": "positive"},
                "no_java": {"key": "no_java", "label": "No Java", "sentiment": "negative"},
            }
        )
        assert "[WANT] Remote only" in result
        assert "[AVOID] No Java" in result


class TestSummaryPrompt:
    def test_is_chat_prompt_template(self) -> None:
        assert isinstance(SUMMARY_PROMPT, ChatPromptTemplate)

    def test_has_required_input_variables(self) -> None:
        assert "user_profile" in SUMMARY_PROMPT.input_variables
        assert "preferences" in SUMMARY_PROMPT.input_variables
        assert "jobs_json" in SUMMARY_PROMPT.input_variables
