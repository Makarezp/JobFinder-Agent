from io import BytesIO
from typing import Any

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
    JOBS_KEY,
    TEXT_RESPONSE_KEY,
)
from app.core.logging import log_timing, request_id_var
from app.core.logging_utils import log_state_snapshot

logger = structlog.get_logger(__name__)


class ChatService:
    def __init__(self, graph: CompiledStateGraph[Any], store: BaseStore) -> None:
        self._graph = graph
        self._store = store

    async def process_message(self, message: str, thread_id: str = DEFAULT_THREAD_ID) -> dict[str, Any]:
        """
        Processes a user message through the LangGraph agent.
        Returns a dictionary suitable for the frontend template.
        """
        logger.info("Processing chat message", extra={"thread_id": thread_id})

        inputs: dict[str, Any] = {
            "messages": [HumanMessage(content=message)],
            "search_attempts": 0,
        }
        config: RunnableConfig = {
            "configurable": {"thread_id": thread_id, "user_id": DEFAULT_USER_ID},
            "metadata": {"request_id": request_id_var.get()},
            "tags": ["chat"],
            "recursion_limit": 30,  # Safety valve: prevent infinite loops
        }

        final_state = inputs
        with log_timing("graph.astream", logger):
            async for state in self._graph.astream(inputs, config=config, stream_mode="values"):
                log_state_snapshot(logger, state, truncate_keys=[CV_RAW_TEXT_KEY])
                final_state = state

        return self._parse_agent_result(final_state, message)

    async def process_cv(self, file_bytes: bytes, filename: str, thread_id: str = DEFAULT_THREAD_ID) -> dict[str, Any]:
        """
        Extracts text from a PDF and injects it into the graph as cv_raw_text.
        The onboarding agent will analyze it and store a structured summary.
        """
        logger.info("Processing CV upload", extra={"cv_filename": filename, "thread_id": thread_id})

        cv_text = self._extract_text_from_pdf(file_bytes)

        config: RunnableConfig = {
            "configurable": {"thread_id": thread_id, "user_id": DEFAULT_USER_ID},
            "metadata": {"request_id": request_id_var.get()},
            "tags": ["upload-cv"],
        }

        # Inject CV text as state + user message — onboarding agent handles the rest
        inputs: dict[str, Any] = {
            "messages": [HumanMessage(content=f"I just uploaded my CV ({filename}). Please analyze it.")],
            CV_RAW_TEXT_KEY: cv_text,
        }

        final_state = inputs
        with log_timing("graph.astream", logger):
            async for state in self._graph.astream(inputs, config=config, stream_mode="values"):
                log_state_snapshot(logger, state, truncate_keys=[CV_RAW_TEXT_KEY])
                final_state = state

        return self._parse_agent_result(final_state, f"Uploaded CV: {filename}")

    def _parse_agent_result(self, result: dict[str, Any], user_message: str) -> dict[str, Any]:
        """
        Parses the LangGraph result to extract the final answer and jobs.
        Handles both onboarding (plain AI messages) and main agent (final_answer tool).
        """
        last_message = result["messages"][-1]
        jobs: list[Any] = []
        ai_content = ""

        if (
            isinstance(last_message, AIMessage)
            and hasattr(last_message, "tool_calls")
            and len(last_message.tool_calls) > 0
            and last_message.tool_calls[0]["name"] == FINAL_ANSWER_TOOL_NAME
        ):
            final_args = last_message.tool_calls[0]["args"]
            ai_content = final_args.get(TEXT_RESPONSE_KEY, "")
            jobs = final_args.get(JOBS_KEY, [])
        else:
            ai_content = last_message.content
            # Handle multipart content if necessary
            if isinstance(ai_content, list):
                text_parts = []
                for part in ai_content:
                    if isinstance(part, str):
                        text_parts.append(part)
                    elif isinstance(part, dict) and "text" in part:
                        text_parts.append(part["text"])
                ai_content = "\n".join(text_parts)

        # Return dict for Jinja2 template
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

    async def get_history(self, thread_id: str = DEFAULT_THREAD_ID) -> list[dict[str, Any]]:
        """
        Retrieves the chat history for a given thread, formatted for the UI.
        Returns a list of message turns (User -> AI).
        """
        logger.info("Fetching chat history", extra={"thread_id": thread_id})

        config: RunnableConfig = {
            "configurable": {"thread_id": thread_id, "user_id": DEFAULT_USER_ID},
        }

        # fetch current state
        state = await self._graph.aget_state(config)
        if not state.values:
            return []

        messages = state.values.get("messages", [])
        history: list[dict[str, Any]] = []

        # Simple pairing strategy: iterate and group Human -> AI
        # We skip SystemMessages.
        # This assumes a somewhat strict turn-taking (Human -> AI -> Human -> AI)
        # adaptable if we have multiple tool calls in between.

        current_turn: dict[str, Any] | None = None

        for msg in messages:
            if isinstance(msg, HumanMessage):
                # Start a new turn
                if current_turn:
                    # if we had a previous turn pending, add it
                    history.append(current_turn)

                current_turn = {"user_message": msg.content, "ai_message": "", "jobs": []}

            elif isinstance(msg, AIMessage):
                # This is the response to the current turn
                if current_turn is None:
                    # AI message without preceding Human? (Maybe greeting or system initiated)
                    continue

                # Parse the AI message
                ai_content = ""
                jobs = []

                if hasattr(msg, "tool_calls") and len(msg.tool_calls) > 0 and msg.tool_calls[0]["name"] == FINAL_ANSWER_TOOL_NAME:
                    final_args = msg.tool_calls[0]["args"]
                    ai_content = final_args.get(TEXT_RESPONSE_KEY, "")
                    jobs = final_args.get(JOBS_KEY, [])
                else:
                    content = msg.content
                    if isinstance(content, list):
                        text_parts = []
                        for part in content:
                            if isinstance(part, str):
                                text_parts.append(part)
                            elif isinstance(part, dict) and "text" in part:
                                text_parts.append(part["text"])
                        ai_content = "\n".join(text_parts)
                    else:
                        ai_content = str(content)

                # Append content (if multiple AI messages in one turn)
                if ai_content:
                    if current_turn["ai_message"]:
                        current_turn["ai_message"] += "\n" + ai_content
                    else:
                        current_turn["ai_message"] = ai_content

                if jobs:
                    current_turn["jobs"].extend(jobs)

        # If there's a dangling turn, add it
        if current_turn:
            history.append(current_turn)

        return history
