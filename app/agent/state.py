from typing import TypedDict, Annotated, List
from langchain_core.messages import BaseMessage
import operator


class AgentState(TypedDict):
    """
    State for the scraper agent.
    """

    messages: Annotated[List[BaseMessage], operator.add]
    url: str | None
    scraped_content: str | None
    loading: bool
