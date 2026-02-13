import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from app.agent.constants import CV_TEXT_KEY, DEFAULT_THREAD_ID, FINAL_ANSWER_TOOL_NAME, JOBS_KEY, TEXT_RESPONSE_KEY
from app.agent.graph import graph

logger = logging.getLogger(__name__)


class ChatService:
    async def process_message(self, message: str, thread_id: str = DEFAULT_THREAD_ID) -> dict[str, Any]:
        """
        Processes a user message through the LangGraph agent.
        Returns a dictionary suitable for the frontend template.
        """
        inputs = {"messages": [HumanMessage(content=message)]}
        config = {"configurable": {"thread_id": thread_id}}

        result = await graph.ainvoke(inputs, config=config)
        return self._parse_agent_result(result, message)

    async def process_cv(self, cv_text: str, filename: str, thread_id: str = DEFAULT_THREAD_ID) -> dict[str, Any]:
        """
        Updates agent state with CV text and triggers a response.
        """
        config = {"configurable": {"thread_id": thread_id}}

        # Update state with CV text
        graph.update_state(config, {CV_TEXT_KEY: cv_text})

        # Trigger follow-up
        inputs = {
            "messages": [
                HumanMessage(
                    content="I just uploaded my CV. Please analyze it and tell me what kind of jobs I should look for."
                )
            ]
        }
        result = await graph.ainvoke(inputs, config=config)
        return self._parse_agent_result(result, f"Uploaded CV: {filename}")

    def _parse_agent_result(self, result: dict[str, Any], user_message: str) -> dict[str, Any]:
        """
        Parses the LangGraph result to extract the final answer and jobs.
        """
        last_message = result["messages"][-1]
        jobs = []
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
