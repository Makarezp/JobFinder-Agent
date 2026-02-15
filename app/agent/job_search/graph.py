import logging

from langgraph.graph import END, START, StateGraph

from app.agent.job_search.nodes import inspect_job, search_jobs
from app.agent.job_search.state import JobSpecialistInput, JobSpecialistState

logger = logging.getLogger(__name__)

# Node constants
SEARCH_NODE = "search_jobs"
INSPECT_NODE = "inspect_job"


def router(state: JobSpecialistState) -> str:
    """Route based on input mode."""
    # input is a JobSpecialistInput object
    # Assuming state["input"] is of type JobSpecialistInput
    input_obj: JobSpecialistInput = state["input"]
    mode = input_obj.mode
    if mode == "search":
        return SEARCH_NODE
    elif mode == "inspect":
        return INSPECT_NODE
    else:
        logger.error(f"Unknown mode: {mode}")
        return END  # type: ignore[no-any-return]


workflow = StateGraph(JobSpecialistState)

workflow.add_node(SEARCH_NODE, search_jobs)
workflow.add_node(INSPECT_NODE, inspect_job)

workflow.add_conditional_edges(
    START,
    router,
    {SEARCH_NODE: SEARCH_NODE, INSPECT_NODE: INSPECT_NODE},
)

workflow.add_edge(SEARCH_NODE, END)
workflow.add_edge(INSPECT_NODE, END)

job_search_graph = workflow.compile()
