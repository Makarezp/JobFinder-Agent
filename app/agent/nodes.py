import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from langsmith import traceable
from langchain_core.messages import SystemMessage
from app.agent.state import AgentState
from app.tools.scraper import scrape_website
from app.tools.adzuna_api import adzuna_api_search
from app.core.config import settings
from langgraph.prebuilt import ToolNode

logger = logging.getLogger(__name__)

# Initialize Model
llm = ChatGoogleGenerativeAI(
    model="gemini-flash-latest", temperature=0, google_api_key=settings.GEMINI_API_KEY
)
tools = [adzuna_api_search, scrape_website]
llm_with_tools = llm.bind_tools(tools)


logger = logging.getLogger(__name__)


# System Prompt
SYSTEM_PROMPT = """You are a helpful job assistant.
When you find job listings using the `adzuna_api_search` tool, you MUST look for "Apply Here" links in the results.
For the most promising or relevant jobs (up to 3), you MUST immediately call the `scrape_website` tool on those "Apply Here" URLs to get more details.
After scraping, you should provide a comprehensive answer that includes the new details found from the job description page (e.g. full requirements, benefits, tech stack).
"""


# Nodes
@traceable
def chatbot(state: AgentState):
    logger.info("Invoking chatbot node")
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    return {"messages": [llm_with_tools.invoke(messages)]}


tool_node = ToolNode(tools=tools)
