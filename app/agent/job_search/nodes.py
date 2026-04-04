import asyncio
import json
from typing import Any

import structlog
from langchain_core.runnables import Runnable

from app.agent.constants import FETCH_NUM_PAGES, SUMMARY_BATCH_SIZE, SUMMARY_LLM_TIMEOUT
from app.agent.job_search.prompts import (
    SUMMARY_PROMPT,
    format_preferences_for_summary,
    format_profile_for_summary,
)
from app.agent.job_search.state import JobSpecialistState
from app.agent.schemas import JobListing, JobSummaryBatch
from app.core.llm import get_summarisation_model
from app.tools.jsearch_api import jsearch_api_search

logger = structlog.get_logger(__name__)

# --- Lazy singleton for summary LLM ---

_summary_llm: Runnable[Any, Any] | None = None


def _get_summary_llm() -> Runnable[Any, Any]:
    global _summary_llm  # noqa: PLW0603
    if _summary_llm is None:
        _summary_llm = get_summarisation_model(temperature=0).with_structured_output(JobSummaryBatch)
    return _summary_llm


# --- Helpers ---


def _chunk_listings(listings: list[JobListing], size: int) -> list[list[JobListing]]:
    """Split listings into sub-lists of `size`."""
    return [listings[i : i + size] for i in range(0, len(listings), size)]


# --- fetch_jobs (called directly, NOT a graph node) ---


def fetch_jobs(state: JobSpecialistState) -> dict[str, Any]:
    """Execute the job search using the JSearch API."""
    logger.info("Node Started: fetch_jobs")
    input_data = state["input"]

    logger.info("Job Specialist: Searching", query=input_data.query, page=input_data.page)

    raw_results = jsearch_api_search.invoke(
        {
            "query": input_data.query,
            "date_posted": input_data.date_posted,
            "remote_only": input_data.remote_only,
            "page": input_data.page,
            "num_pages": FETCH_NUM_PAGES,
            "country": input_data.country,
        }
    )

    if isinstance(raw_results, str):
        logger.error("JSearch tool returned an error", error=raw_results)
        return {"search_results": []}

    listings: list[JobListing] = []
    for r in raw_results:
        try:
            listing = JobListing(
                id=r.get("id", ""),
                title=r.get("title", "N/A"),
                company=r.get("company", "N/A"),
                location=r.get("location", ""),
                salary=r.get("salary"),
                description=r.get("description", ""),
                full_description=r.get("full_description"),
                apply_link=r.get("apply_link", ""),
            )
            listings.append(listing)
        except (ValueError, TypeError) as e:
            logger.warning("Failed to parse JobListing", error=str(e), data=r)

    job_summaries = [f"{job.title} @ {job.company}" for job in listings]
    logger.info("Node Completed: fetch_jobs", result_count=len(listings), job_summaries=job_summaries)
    return {"search_results": listings}


# --- Single-batch summarization ---


async def _summarize_batch(
    batch: list[JobListing],
    profile: dict[str, Any] | None,
    preferences: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Summarize a single batch of job listings via LLM. Returns [] on any failure."""
    try:
        messages = SUMMARY_PROMPT.format_messages(
            user_profile=format_profile_for_summary(profile),
            preferences=format_preferences_for_summary(preferences),
            jobs_json=json.dumps([j.model_dump() for j in batch]),
        )
        result: JobSummaryBatch = await _get_summary_llm().ainvoke(messages)  # type: ignore[assignment]

        # Validate count — keep only summaries with matching job_ids
        batch_ids = {j.id for j in batch}
        valid = [s for s in result.summaries if s.job_id in batch_ids]

        if len(valid) != len(batch):
            logger.warning(
                "Summary count mismatch",
                expected=len(batch),
                received=len(result.summaries),
                valid=len(valid),
            )

        return [s.model_dump() for s in valid]

    except Exception:
        logger.exception("Summary batch failed")
        return []


# --- Graph node: summarize_jobs_parallel ---


async def summarize_jobs_parallel(state: JobSpecialistState) -> dict[str, Any]:
    """Chunk job listings and summarize all batches in parallel with timeout."""
    logger.info("Node Started: summarize_jobs_parallel")

    search_results = state.get("search_results") or []
    if not search_results:
        logger.info("Node Completed: summarize_jobs_parallel", summary_count=0, input_count=0)
        return {"summaries": []}

    profile = state.get("user_profile")
    prefs = state.get("preferences")
    chunks = _chunk_listings(search_results, SUMMARY_BATCH_SIZE)

    async def _timed_batch(chunk: list[JobListing]) -> list[dict[str, Any]]:
        try:
            return await asyncio.wait_for(
                _summarize_batch(chunk, profile, prefs),
                timeout=SUMMARY_LLM_TIMEOUT,
            )
        except TimeoutError:
            logger.warning("Summary batch timed out", batch_size=len(chunk))
            return []

    results = await asyncio.gather(*[_timed_batch(chunk) for chunk in chunks])
    all_summaries = [s for batch_result in results for s in batch_result]

    logger.info(
        "Node Completed: summarize_jobs_parallel",
        summary_count=len(all_summaries),
        input_count=len(search_results),
    )
    return {"summaries": all_summaries}


# --- Graph node: finalize_state ---


def finalize_state(state: JobSpecialistState) -> dict[str, Any]:
    """Merge AI summaries into JobListings and separate UI payload from LLM context."""
    logger.info("Node Started: finalize_state")

    search_results = state.get("search_results") or []
    summaries: list[dict[str, Any]] = state.get("summaries") or []

    if not search_results:
        content = json.dumps({"jobs": [], "note": "No jobs found."})
        logger.info("Node Completed: finalize_state", staged_count=0, summarized_count=0)
        return {"job_payloads": [], "tool_message_content": content}

    summary_by_id: dict[str, dict[str, Any]] = {
        s["job_id"]: {"description": s["description"], "recommend": s.get("recommend", True)} for s in summaries
    }

    job_payloads: list[dict[str, Any]] = []
    tool_jobs: list[dict[str, Any]] = []

    for job in search_results:
        summary = summary_by_id.get(job.id)
        if summary:
            job.description = summary["description"]
        payload = job.model_dump()

        # tool_message_content: strip full_description, include all jobs (chatbot sees everything)
        entry = {k: v for k, v in payload.items() if k != "full_description"}
        tool_jobs.append(entry)

        # job_payloads (UI): only include recommended jobs or unsummarized jobs (safe default)
        if summary is None or summary.get("recommend", True):
            job_payloads.append(payload)

    tool_message_content = json.dumps(
        {"jobs": tool_jobs, "note": f"Summarized {len(tool_jobs)} jobs."},
    )

    summarized_count = sum(1 for j_id in summary_by_id if any(j.id == j_id for j in search_results))
    filtered_count = len(tool_jobs) - len(job_payloads)
    logger.info(
        "Node Completed: finalize_state",
        staged_count=len(job_payloads),
        summarized_count=summarized_count,
        filtered_count=filtered_count,
    )
    return {"job_payloads": job_payloads, "tool_message_content": tool_message_content}
