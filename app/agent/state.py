import operator
from typing import Annotated, Any, NotRequired, TypedDict

from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """Shared state for the dual-agent graph (onboarding + main).

    Fields are populated by nodes and read by routers. ``fetch_profile``
    hydrates ``user_profile``, ``preferences``, and ``recent_decisions``
    from the LangGraph Store on every main-agent turn.

    Note on dict[str, Any] typing: Pydantic models (UserProfile, Preference,
    DecisionLog) are used for validation, but ``.model_dump()`` is called
    before writing to state because LangGraph's checkpointer requires
    JSON-serialisable TypedDict values.
    """

    messages: Annotated[list[BaseMessage], operator.add]
    user_profile: dict[str, Any] | None
    preferences: dict[str, Any] | None
    onboarding_complete: bool
    cv_raw_text: str | None
    search_attempts: int
    recent_decisions: NotRequired[list[dict[str, Any]]]
