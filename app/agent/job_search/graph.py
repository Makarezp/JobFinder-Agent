import structlog
from langgraph.graph import END, START, StateGraph

from app.agent.job_search.nodes import finalize_state, summarize_jobs_parallel
from app.agent.job_search.state import JobSpecialistState

logger = structlog.get_logger(__name__)

SUMMARIZE_NODE = "summarize_jobs_parallel"
FINALIZE_NODE = "finalize_state"

workflow = StateGraph(JobSpecialistState)
workflow.add_node(SUMMARIZE_NODE, summarize_jobs_parallel)
workflow.add_node(FINALIZE_NODE, finalize_state)
workflow.add_edge(START, SUMMARIZE_NODE)
workflow.add_edge(SUMMARIZE_NODE, FINALIZE_NODE)
workflow.add_edge(FINALIZE_NODE, END)

job_search_graph = workflow.compile()
