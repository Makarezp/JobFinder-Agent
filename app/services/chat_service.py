import logging
from io import BytesIO
from typing import Any

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

logger = logging.getLogger(__name__)


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

        inputs: dict[str, Any] = {"messages": [HumanMessage(content=message)]}
        config: RunnableConfig = {
            "configurable": {"thread_id": thread_id, "user_id": DEFAULT_USER_ID},
            "metadata": {"request_id": request_id_var.get()},
            "tags": ["chat"],
        }

        with log_timing("graph.ainvoke", logger):
            result = await self._graph.ainvoke(inputs, config=config)
        return self._parse_agent_result(result, message)

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

        with log_timing("graph.ainvoke", logger):
            result = await self._graph.ainvoke(inputs, config=config)
        return self._parse_agent_result(result, f"Uploaded CV: {filename}")

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
