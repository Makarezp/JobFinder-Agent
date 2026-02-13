import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from langsmith import traceable
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode

from app.agent.state import AgentState
from app.agent.schemas import AgentResponse, JobListing
from app.tools.scraper import scrape_website
from app.tools.adzuna_api import adzuna_api_search
from app.agent.constants import (
    CV_TEXT_KEY,
    MESSAGES_KEY,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

# System Prompt
# System Prompt
SYSTEM_PROMPT = """You are a helpful job assistant.

**JOB SEARCH INSTRUCTIONS:**
1.  **Analyze the User's Request & CV:**
    *   If a CV is provided, **YOU MUST** prioritize the skills, job titles, and technologies found in the CV.
    *   Do NOT use generic terms like "Software Engineer" if more specific terms (e.g., "Android Developer", "Kotlin", "React Native") are available in the CV or user request.
    *   Construct your `adzuna_api_search` queries using these specific keywords.

2.  **Search & Refine:**
    *   Call `adzuna_api_search` with these targeted keywords.
    *   Look for "Apply Here" links in the results.

3.  **Scrape for Details (Mandatory for Top Jobs):**
    *   For the most promising or relevant jobs (up to 3), you **MUST** immediately call the `scrape_website` tool on those "Apply Here" URLs.
    *   This is crucial to get full job descriptions, benefits, and requirements.

4.  **Final Output:**
    *   Analyze the scraped data.
    *   **YOU MUST** call the `final_answer` tool to present the results.
    *   Populate `text_response` with a helpful summary.
    *   Populate `jobs` with the structured data.
"""


@tool(args_schema=AgentResponse)
def final_answer(text_response: str, jobs: list[JobListing] = []):
    """Present the final response to the user with optional job listings."""
    pass


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
def chatbot(state: AgentState):
    logger.info("Invoking chatbot node")

    messages = state[MESSAGES_KEY]

    # Add System Prompt
    system_messages = [SystemMessage(content=SYSTEM_PROMPT)]

    # Add CV Context if available
    if state.get(CV_TEXT_KEY):
        cv_context = f"\n\nUser's CV Content:\n{state[CV_TEXT_KEY]}\n\nUse this to personalize job recommendations."
        system_messages.append(SystemMessage(content=cv_context))

    messages = system_messages + messages
    return {"messages": [llm_with_tools.invoke(messages)]}


tool_node = ToolNode(tools=tools)
