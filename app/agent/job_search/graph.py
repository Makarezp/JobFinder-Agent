import structlog
from langgraph.graph import END, START, StateGraph

from app.agent.job_search.nodes import search_jobs
from app.agent.job_search.state import JobSpecialistState

logger = structlog.get_logger(__name__)

SEARCH_NODE = "search_jobs"

workflow = StateGraph(JobSpecialistState)

workflow.add_node(SEARCH_NODE, search_jobs)
workflow.add_edge(START, SEARCH_NODE)
workflow.add_edge(SEARCH_NODE, END)

job_search_graph = workflow.compile()
