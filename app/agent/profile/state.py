import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage


class ProfileAgentState(TypedDict):
    """State schema for the standalone Profile Agent.

    Handles CV parsing, profile building, and preference capture.

    Intentionally excludes ``onboarding_complete`` (routing is handled
    externally by ``ChatService``), ``search_attempts``, and
    ``recent_decisions`` (the Profile Agent does not search for jobs).
    """

    messages: Annotated[list[BaseMessage], operator.add]
    user_profile: dict[str, Any] | None
    preferences: dict[str, Any] | None
    cv_raw_text: str | None
