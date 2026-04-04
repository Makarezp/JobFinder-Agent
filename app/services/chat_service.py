import hashlib
from io import BytesIO
from typing import Any, Literal

import structlog
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore
from pypdf import PdfReader

from app.agent.constants import (
    CV_RAW_TEXT_KEY,
    DEFAULT_THREAD_ID,
    DEFAULT_USER_ID,
    FINAL_ANSWER_TOOL_NAME,
    SELECTED_JOB_IDS_KEY,
    TEXT_RESPONSE_KEY,
)
from app.core.logging import log_timing, request_id_var
from app.core.snapshot_logging_utils import log_state_snapshot
from app.services.profile_service import ProfileService

logger = structlog.get_logger(__name__)


class ChatService:
    def __init__(
        self,
        discovery_graph: CompiledStateGraph[Any],
        profile_graph: CompiledStateGraph[Any],
        store: BaseStore,
        profile_service: ProfileService,
    ) -> None:
        self._discovery_graph = discovery_graph
        self._profile_graph = profile_graph
        self._store = store
        self._profile_service = profile_service

    def _get_graph(self, workspace: Literal["discovery", "profile"]) -> CompiledStateGraph[Any]:
        if workspace == "profile":
            return self._profile_graph
        return self._discovery_graph

    async def process_message(
        self, message: str, thread_id: str = DEFAULT_THREAD_ID, workspace: Literal["discovery", "profile"] = "discovery"
    ) -> dict[str, Any]:
        """
        Processes a user message through the LangGraph agent.
        Returns a dictionary suitable for the frontend template.
        """
        logger.info("Processing chat message", thread_id=thread_id, workspace=workspace)

        inputs: dict[str, Any] = {"messages": [HumanMessage(content=message)]}
        if workspace == "discovery":
            inputs["search_attempts"] = 0

        config: RunnableConfig = {
            "configurable": {"thread_id": f"{thread_id}_{workspace}", "user_id": DEFAULT_USER_ID},
            "metadata": {"request_id": request_id_var.get()},
            "tags": ["chat"],
            "recursion_limit": 30,
        }

        graph = self._get_graph(workspace)
        last_state = inputs
        with log_timing("graph.astream", logger):
            async for state in graph.astream(inputs, config=config, stream_mode="values"):
                log_state_snapshot(state, truncate_keys=[CV_RAW_TEXT_KEY], previous_state=last_state)
                last_state = state

        result = self._parse_agent_result(last_state, message)
        if result["jobs"]:
            await self._profile_service.add_pending_jobs(result["jobs"], DEFAULT_USER_ID)
        return result

    async def process_cv(self, file_bytes: bytes, filename: str, thread_id: str = DEFAULT_THREAD_ID) -> dict[str, Any]:
        """
        Extracts text from a PDF and injects it into the profile graph as cv_raw_text.
        CV upload is always a profile workspace action.
        """
        logger.info("Processing CV upload", cv_filename=filename, thread_id=thread_id)

        cv_text = self._extract_text_from_pdf(file_bytes)

        config: RunnableConfig = {
            "configurable": {"thread_id": f"{thread_id}_profile", "user_id": DEFAULT_USER_ID},
            "metadata": {"request_id": request_id_var.get()},
            "tags": ["upload-cv"],
        }

        inputs: dict[str, Any] = {
            "messages": [HumanMessage(content=f"I just uploaded my CV ({filename}). Please analyze it.")],
            CV_RAW_TEXT_KEY: cv_text,
        }

        last_state = inputs
        with log_timing("graph.astream", logger):
            async for state in self._profile_graph.astream(inputs, config=config, stream_mode="values"):
                log_state_snapshot(state, truncate_keys=[CV_RAW_TEXT_KEY], previous_state=last_state)
                last_state = state

        result = self._parse_agent_result(last_state, f"Uploaded CV: {filename}")
        return result

    @staticmethod
    def _extract_ai_content(msg: AIMessage) -> tuple[str, list[str]]:
        """Extract text and selected job IDs from an AIMessage.

        Handles two formats:
        - final_answer tool call: structured text_response + selected_job_ids
        - Plain AI message: may be a string or a multipart list
          (Gemini may return multipart content as a list of text/dict segments)
        """
        if isinstance(msg, AIMessage) and msg.tool_calls and msg.tool_calls[0]["name"] == FINAL_ANSWER_TOOL_NAME:
            final_args = msg.tool_calls[0]["args"]
            return (
                final_args.get(TEXT_RESPONSE_KEY, ""),
                final_args.get(SELECTED_JOB_IDS_KEY, []),
            )

        content = msg.content
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, str):
                    text_parts.append(part)
                elif isinstance(part, dict) and "text" in part:
                    text_parts.append(part["text"])
            return "\n".join(text_parts), []

        return str(content), []

    def _parse_agent_result(self, result: dict[str, Any], user_message: str) -> dict[str, Any]:
        """
        Parses the LangGraph result to extract the final answer and jobs.
        Handles both onboarding (plain AI messages) and main agent (final_answer tool).
        """
        messages = result["messages"]
        last_ai_message = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)

        if not last_ai_message:
            return {
                "user_message": user_message,
                "ai_message": "I apologize, but I couldn't generate a response. Please try asking again.",
                "jobs": [],
            }

        ai_content, selected_ids = self._extract_ai_content(last_ai_message)

        # Map the agent's selected IDs back to full pipeline data.
        # Only adds jobs when the LLM explicitly selects via IDs — no fallback.
        # job_payloads persists in the checkpoint, so without this guard a non-search
        # turn would re-add stale jobs to the Deck.
        job_payloads: list[dict[str, Any]] = result.get("job_payloads", [])
        jobs: list[dict[str, Any]] = []
        if job_payloads and selected_ids:
            payload_by_id = {j["id"]: j for j in job_payloads}
            for job_id in selected_ids:
                if job_id in payload_by_id:
                    jobs.append(payload_by_id[job_id])
                else:
                    logger.warning("Unknown job ID ignored", job_id=job_id, available=len(payload_by_id))

        if not ai_content and not jobs:
            ai_content = "I apologize, but I couldn't generate a response. Please try asking again."

        for job in jobs:
            if not job.get("id"):
                slug = f"{job.get('company', '')}{job.get('title', '')}{job.get('apply_link', '')}".encode()
                job["id"] = hashlib.md5(slug).hexdigest()[:12]  # noqa: S324 — not used for security

        return {
            "user_message": user_message,
            "ai_message": ai_content,
            "jobs": jobs,
        }

    @staticmethod
    def _extract_text_from_pdf(file_bytes: bytes) -> str:
        """Extract text content from raw PDF bytes."""
        pdf = PdfReader(BytesIO(file_bytes))
        return "\n".join(page.extract_text() for page in pdf.pages)

    async def get_history(self, thread_id: str = DEFAULT_THREAD_ID, workspace: Literal["discovery", "profile"] = "discovery") -> list[dict[str, Any]]:
        """
        Retrieves the chat history for a given thread, formatted for the UI.
        Returns a list of message turns (User -> AI).
        """
        logger.info("Fetching chat history", thread_id=thread_id, workspace=workspace)

        config: RunnableConfig = {
            "configurable": {"thread_id": f"{thread_id}_{workspace}", "user_id": DEFAULT_USER_ID},
        }

        graph = self._get_graph(workspace)
        state = await graph.aget_state(config)
        if not state.values:
            return []

        messages = state.values.get("messages", [])
        history: list[dict[str, Any]] = []

        # Assumes strict turn-taking (Human → AI). Tool call messages in between
        # are skipped; only the final AIMessage per turn is surfaced.

        current_turn: dict[str, Any] | None = None

        for msg in messages:
            # Filter out internal system trigger messages — never expose to the frontend
            if isinstance(msg, HumanMessage) and str(msg.content).startswith("[SYSTEM TRIGGER]"):
                continue
            if isinstance(msg, HumanMessage):
                # Start a new turn
                if current_turn:
                    # if we had a previous turn pending, add it
                    history.append(current_turn)

                current_turn = {"user_message": msg.content, "ai_message": "", "jobs": []}

            elif isinstance(msg, AIMessage):
                if current_turn is None:
                    continue

                ai_content, _ = self._extract_ai_content(msg)

                # Append content (if multiple AI messages in one turn)
                if ai_content:
                    if current_turn["ai_message"]:
                        current_turn["ai_message"] += "\n" + ai_content
                    else:
                        current_turn["ai_message"] = ai_content

        # If there's a dangling turn, add it
        if current_turn:
            history.append(current_turn)

        return history
