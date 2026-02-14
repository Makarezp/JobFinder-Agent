import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """
    State for the agent graph.
    """

    messages: Annotated[list[BaseMessage], operator.add]
    user_profile: dict[str, Any] | None
    preferences: dict[str, Any] | None
    onboarding_complete: bool
    cv_raw_text: str | None
    active_agent: str
