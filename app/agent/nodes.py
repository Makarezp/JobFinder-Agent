import logging
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, ToolMessage, AIMessage
from langsmith import traceable
from app.agent.state import AgentState
from app.tools.scraper import scrape_website
from app.core.config import settings
from langgraph.prebuilt import ToolNode

# Initialize Model
llm = ChatGoogleGenerativeAI(
    model="gemini-flash-latest", temperature=0, google_api_key=settings.GEMINI_API_KEY
)
tools = [scrape_website]
llm_with_tools = llm.bind_tools(tools)


logger = logging.getLogger(__name__)


# Nodes
@traceable
def chatbot(state: AgentState):
    logger.info("Invoking chatbot node")
    return {"messages": [llm_with_tools.invoke(state["messages"])]}


tool_node = ToolNode(tools=tools)
