import logging

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import ToolNode
from langsmith import traceable

from app.agent.constants import (
    CV_TEXT_KEY,
    MESSAGES_KEY,
)
from app.agent.prompts.agent_prompts import SYSTEM_PROMPT
from app.agent.schemas import AgentResponse, JobListing
from app.agent.state import AgentState
from app.core.config import settings
from app.tools.adzuna_api import adzuna_api_search
from app.tools.scraper import scrape_website

logger = logging.getLogger(__name__)


@tool(args_schema=AgentResponse)
def final_answer(text_response: str, jobs: list[JobListing] | None = None) -> str:
    """Present the final response to the user with optional job listings."""
    if jobs is None:
        jobs = []
    return "Final Answer Processed"


# Initialize Model
llm = ChatGoogleGenerativeAI(
    model=settings.GEMINI_MODEL_NAME,
    temperature=0,
    google_api_key=settings.GEMINI_API_KEY,
)
tools = [adzuna_api_search, scrape_website, final_answer]
llm_with_tools = llm.bind_tools(tools)


# Nodes
@traceable
def chatbot(state: AgentState) -> dict[str, list[BaseMessage]]:
    logger.info("Invoking chatbot node")

    messages = state[MESSAGES_KEY]  # type: ignore

    # Add System Prompt
    system_messages = [SystemMessage(content=SYSTEM_PROMPT)]

    # Add CV Context if available
    if state.get(CV_TEXT_KEY):
        cv_context = f"\n\nUser's CV Content:\n{state[CV_TEXT_KEY]}\n\nUse this to personalize job recommendations."  # type: ignore
        system_messages.append(SystemMessage(content=cv_context))

    messages = system_messages + messages
    return {"messages": [llm_with_tools.invoke(messages)]}


tool_node = ToolNode(tools=tools)
