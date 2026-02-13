import logging
import traceback
from io import BytesIO
from pathlib import Path

import markdown
from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.templating import Jinja2Templates
from pypdf import PdfReader

from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.post("/chat")
async def chat_endpoint(request: Request, message: str = Form(...)) -> Response:  # type: ignore
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    try:
        service = ChatService()
        result = await service.process_message(message)

        # Format Markdown to HTML for rendering
        if result.get("ai_message"):
            result["ai_message"] = markdown.markdown(result["ai_message"])

        return templates.TemplateResponse(request, "components/chat_message.html", result)

    except Exception as e:
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
async def upload_cv(request: Request, file: UploadFile = File(...)) -> Response:  # type: ignore
    try:
        # Read PDF content
        content = await file.read()
        pdf = PdfReader(BytesIO(content))
        text = ""
        for page in pdf.pages:
            text += page.extract_text() + "\n"

        # Delegate to Service Layer
        service = ChatService()
        result = await service.process_cv(text, filename=file.filename or "unknown")

        # Format Markdown to HTML for rendering
        if result.get("ai_message"):
            result["ai_message"] = markdown.markdown(result["ai_message"])

        return templates.TemplateResponse(request, "components/chat_message.html", result)

    except Exception as e:
        logger.error(f"Error processing CV upload: {e}\n{traceback.format_exc()}")
        return templates.TemplateResponse(
            request,
            "components/chat_message.html",
            {
                "user_message": "CV Upload Failed",
                "ai_message": f"<p class='text-red-500'>Error processing CV: {str(e)}</p>",
            },
        )
