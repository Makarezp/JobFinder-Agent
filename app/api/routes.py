from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.templating import Jinja2Templates
from langchain_core.messages import HumanMessage
from app.agent.graph import graph
from app.agent.state import AgentState
from pathlib import Path
import logging
import markdown
from fastapi import UploadFile, File
from pypdf import PdfReader
from io import BytesIO

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


@router.post("/upload-cv")
async def upload_cv(request: Request, file: UploadFile = File(...)):
    try:
        # Read PDF content
        content = await file.read()
        pdf = PdfReader(BytesIO(content))
        text = ""
        for page in pdf.pages:
            text += page.extract_text() + "\n"

        # Update Agent State with CV text
        thread_id = "default_user_session"
        config = {"configurable": {"thread_id": thread_id}}

        # We need to update the state. LangGraph's update_state usage:
        # graph.update_state(config, {"cv_text": text})
        graph.update_state(config, {"cv_text": text})

        # Trigger agent response acknowledging the upload
        inputs = {
            "messages": [
                HumanMessage(
                    content="I just uploaded my CV. Please analyze it and tell me what kind of jobs I should look for based on my skills."
                )
            ]
        }
        result = await graph.ainvoke(inputs, config=config)

        last_message = result["messages"][-1]
        ai_content = last_message.content

        # Handle multipart content (copy-paste from chat endpoint logic for now, refactor later)
        if isinstance(ai_content, list):
            text_parts = []
            for part in ai_content:
                if isinstance(part, str):
                    text_parts.append(part)
                elif isinstance(part, dict) and "text" in part:
                    text_parts.append(part["text"])
            ai_content = "\n".join(text_parts)

        ai_content_html = markdown.markdown(ai_content)

        return templates.TemplateResponse(
            request,
            "components/chat_message.html",
            {
                "user_message": f"Uploaded CV: {file.filename}",
                "ai_message": ai_content_html,
            },
        )

    except Exception as e:
        logger.error(f"Error processing CV upload: {e}")
        return templates.TemplateResponse(
            request,
            "components/chat_message.html",
            {
                "user_message": "CV Upload Failed",
                "ai_message": f"<p class='text-red-500'>Error processing CV: {str(e)}</p>",
            },
        )
