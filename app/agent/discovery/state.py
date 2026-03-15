import operator
from typing import Annotated, Any, NotRequired, TypedDict

from langchain_core.messages import BaseMessage


class DiscoveryAgentState(TypedDict):
    """State schema for the standalone Discovery Agent.

    ``user_profile``, ``preferences``, and ``recent_decisions`` are hydrated
    from the LangGraph Store via ``fetch_profile`` on every turn.

    Intentionally excludes ``onboarding_complete`` (routing is handled
    externally by ``ChatService``) and ``cv_raw_text`` (the Discovery Agent
    never processes CVs).
    """

    messages: Annotated[list[BaseMessage], operator.add]
    user_profile: dict[str, Any] | None
    preferences: dict[str, Any] | None
    search_attempts: int
    recent_decisions: NotRequired[list[dict[str, Any]]]
    job_payloads: NotRequired[list[dict[str, Any]]]
    search_ledger: NotRequired[list[dict[str, Any]]]
