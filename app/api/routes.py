from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.templating import Jinja2Templates
from langchain_core.messages import HumanMessage
from app.agent.graph import graph
from app.agent.state import AgentState
from pathlib import Path
import logging
import markdown

logger = logging.getLogger(__name__)

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.post("/chat")
async def chat_endpoint(request: Request, message: str = Form(...)):
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    # Run Agent
    try:
        inputs = {"messages": [HumanMessage(content=message)]}

        # Use a consistent thread_id for conversation history
        # In a real app, this would come from a session or user ID
        thread_id = "default_user_session"
        config = {"configurable": {"thread_id": thread_id}}

        # Invoke the graph with config
        result = await graph.ainvoke(inputs, config=config)

        last_message = result["messages"][-1]
        ai_content = last_message.content

        if isinstance(ai_content, list):
            # Hande multipart content (e.g. text + tool_use)
            # We want to extract the text parts
            text_parts = []
            for part in ai_content:
                if isinstance(part, str):
                    text_parts.append(part)
                elif isinstance(part, dict) and "text" in part:
                    text_parts.append(part["text"])
            ai_content = "\n".join(text_parts)

        logger.info(f"AI Response: {ai_content}")

        # Convert Markdown to HTML for rendering
        ai_content_html = markdown.markdown(ai_content)

        return templates.TemplateResponse(
            request,
            "components/chat_message.html",
            {
                "user_message": message,
                "ai_message": ai_content_html,
            },
        )
    except Exception as e:
        import traceback

        logger.error(f"Error processing chat request: {e}\n{traceback.format_exc()}")
        return templates.TemplateResponse(
            request,
            "components/chat_message.html",
            {
                "user_message": message,
                "ai_message": f"<p class='text-red-500'>Error: {str(e)}</p>",
            },
        )
