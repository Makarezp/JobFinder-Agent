import asyncio
import functools
import json
from typing import Any, cast

import structlog
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.store.base import BaseStore

from app.agent.constants import (
    DEFAULT_USER_ID,
    DISCOVERY_CHATBOT_NODE,
    DISCOVERY_FETCH_PROFILE_NODE,
    DISCOVERY_JOB_SPECIALIST_NODE,
    DISCOVERY_TOOLS_NODE,
    FINAL_ANSWER_TOOL_NAME,
    MAX_SEARCH_ATTEMPTS,
)
from app.agent.discovery.state import DiscoveryAgentState
from app.agent.job_search.graph import job_search_graph
from app.agent.job_search.nodes import fetch_jobs
from app.agent.job_search.state import JobSpecialistState
from app.agent.main.nodes import fetch_profile, main_chatbot, route_main
from app.agent.main.tools import main_tools
from app.agent.schemas import JobListing, JobSpecialistInput
from app.services.profile_service import ProfileService

logger = structlog.get_logger(__name__)


def _split_fresh_seen(results: list[JobListing], seen_ids: set[str]) -> tuple[list[JobListing], list[JobListing]]:
    """Partition search results into fresh (unseen) and previously seen listings."""
    fresh = [r for r in results if r.id not in seen_ids]
    seen = [r for r in results if r.id in seen_ids]
    return fresh, seen


async def _run_single_job_search(
    tool_call: Any,
    seen_ids: set[str],
    user_profile: dict[str, Any] | None,
    preferences: dict[str, Any] | None,
    profile_service: ProfileService,
) -> tuple[ToolMessage, list[dict[str, Any]], list[JobListing]]:
    """
    Execute one job_specialist_tool call: fetch → dedup → summarize → finalize.
    Returns (ToolMessage for LLM context, job_payloads for UI, fresh listings to mark seen).

    ``seen_ids`` is passed in from the caller so that all parallel searches
    share the same snapshot — avoids a race where Search A marks a job seen
    before Search B checks, causing Search B to demote it to identity-only.
    """
    tool_call_id = tool_call["id"]
    try:
        args = tool_call["args"]
        input_data = JobSpecialistInput(**args)
    except Exception as e:
        return ToolMessage(content=f"Error parsing input: {e}", tool_call_id=tool_call_id), [], []

    # 1. Fetch jobs directly (not a graph node)
    fetch_state: JobSpecialistState = {
        "input": input_data,
        "search_results": None,
        "user_profile": None,
        "preferences": None,
    }
    fetch_result = fetch_jobs(fetch_state)
    all_listings: list[JobListing] = fetch_result.get("search_results", [])

    # 2. Dedup using the shared seen_ids snapshot (no store writes here)
    fresh, seen = _split_fresh_seen(all_listings, seen_ids)

    # 2.5 Log this search to the ledger (before subgraph — survives summarisation failures)
    await profile_service.log_search(
        input_data=input_data,
        results_count=len(all_listings),
        fresh_count=len(fresh),
    )

    # 3. Invoke 2-node subgraph (summarize → finalize) with fresh-only jobs
    subgraph_state: JobSpecialistState = {
        "input": input_data,
        "search_results": fresh,
        "user_profile": user_profile,
        "preferences": preferences,
    }
    result = await job_search_graph.ainvoke(cast(Any, subgraph_state))

    job_payloads: list[dict[str, Any]] = result.get("job_payloads", [])
    tool_message_content: str = result.get("tool_message_content", "")

    # 4. Append seen jobs as minimal identity entries to tool_message_content
    if seen:
        seen_payload = [{"id": r.id, "title": r.title, "company": r.company, "location": r.location} for r in seen]
        try:
            parsed = json.loads(tool_message_content)
            parsed["seen"] = seen_payload
            tool_message_content = json.dumps(parsed)
        except (json.JSONDecodeError, TypeError):
            tool_message_content = json.dumps({"jobs": [], "seen": seen_payload, "note": "Parse error."})

    return ToolMessage(content=tool_message_content, tool_call_id=tool_call_id), job_payloads, fresh


async def call_job_specialist(
    state: DiscoveryAgentState,
    profile_service: ProfileService,
) -> dict[str, Any]:
    """Invokes the Job Specialist subgraph for all parallel tool calls in the last message."""
    messages = state["messages"]
    last_message = messages[-1]
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {"messages": []}

    current_attempts = state.get("search_attempts", 0)

    # Loop protection — answer all tool calls with an error message
    if current_attempts >= MAX_SEARCH_ATTEMPTS:
        logger.warning("Loop protection: max search attempts reached", tool_calls=len(last_message.tool_calls))
        tool_msgs = [
            ToolMessage(content="System: Max search attempts reached. You must provide a final answer stopping the search.", tool_call_id=tc["id"])
            for tc in last_message.tool_calls
        ]
        return {"messages": tool_msgs, "search_attempts": current_attempts + 1}

    tool_messages = []
    job_tool_calls_to_run = []

    # Normal execution, responding to ALL tool calls to appease strict LLMs
    for tc in last_message.tool_calls:
        if tc["name"] == "job_specialist_tool":
            job_tool_calls_to_run.append(tc)
        else:
            tool_messages.append(
                ToolMessage(content=f"Error: {tc['name']} cannot be combined with job_specialist_tool. Ignored.", tool_call_id=tc["id"])
            )

    all_job_payloads: list[dict[str, Any]] = []

    if job_tool_calls_to_run:
        user_profile = state.get("user_profile")
        preferences = state.get("preferences")

        # Snapshot seen IDs once so all parallel searches share the same view.
        # This prevents a race where Search A marks a job seen before Search B
        # checks, causing Search B to demote a perfectly valid job to "seen".
        seen_ids = await profile_service.get_seen_job_ids(DEFAULT_USER_ID)

        results = await asyncio.gather(
            *[_run_single_job_search(tc, seen_ids, user_profile, preferences, profile_service) for tc in job_tool_calls_to_run]
        )

        # Mark all freshly processed jobs as seen in a single batch after all
        # searches complete — no store writes happen inside the parallel fan-out.
        all_fresh: list[JobListing] = []
        for _, _, fresh in results:
            all_fresh.extend(fresh)
        if all_fresh:
            await profile_service.mark_jobs_seen(all_fresh, DEFAULT_USER_ID)

        for tool_msg, job_payloads, _ in results:
            tool_messages.append(tool_msg)
            all_job_payloads.extend(job_payloads)

    return {
        "messages": tool_messages,
        "search_attempts": current_attempts + 1,
        "job_payloads": all_job_payloads,
    }


def route_after_tools(state: DiscoveryAgentState) -> str:
    """Route output of ToolNode. If final_answer was called, end the graph."""
    messages = state["messages"]
    last_ai_message = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
    if last_ai_message and last_ai_message.tool_calls:
        if any(tc["name"] == FINAL_ANSWER_TOOL_NAME for tc in last_ai_message.tool_calls):
            return str(END)
    return DISCOVERY_CHATBOT_NODE


def get_discovery_graph(checkpointer: Any, store: BaseStore) -> CompiledStateGraph[Any]:
    """Build and compile the standalone Discovery Agent graph."""
    profile_service = ProfileService(store)
    builder = StateGraph(DiscoveryAgentState)

    builder.add_node(DISCOVERY_FETCH_PROFILE_NODE, functools.partial(fetch_profile, store=store))
    builder.add_node(DISCOVERY_CHATBOT_NODE, main_chatbot)
    builder.add_node(DISCOVERY_TOOLS_NODE, ToolNode(tools=main_tools))
    builder.add_node(DISCOVERY_JOB_SPECIALIST_NODE, functools.partial(call_job_specialist, profile_service=profile_service))

    builder.add_edge(START, DISCOVERY_FETCH_PROFILE_NODE)
    builder.add_edge(DISCOVERY_FETCH_PROFILE_NODE, DISCOVERY_CHATBOT_NODE)
    builder.add_conditional_edges(
        DISCOVERY_CHATBOT_NODE,
        route_main,
        {
            DISCOVERY_TOOLS_NODE: DISCOVERY_TOOLS_NODE,
            DISCOVERY_JOB_SPECIALIST_NODE: DISCOVERY_JOB_SPECIALIST_NODE,
            END: END,
        },
    )
    builder.add_conditional_edges(
        DISCOVERY_TOOLS_NODE,
        route_after_tools,
        {
            DISCOVERY_CHATBOT_NODE: DISCOVERY_CHATBOT_NODE,
            END: END,
        },
    )
    builder.add_edge(DISCOVERY_JOB_SPECIALIST_NODE, DISCOVERY_CHATBOT_NODE)

    return builder.compile(checkpointer=checkpointer, store=store)
