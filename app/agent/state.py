import operator
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """
    State for the scraper agent.
    """

    messages: Annotated[list[BaseMessage], operator.add]
    url: str | None
    scraped_content: str | None
    cv_text: str | None
    loading: bool
