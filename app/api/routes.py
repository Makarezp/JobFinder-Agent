import logging
import traceback
from pathlib import Path

import markdown as md
from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.templating import Jinja2Templates

from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["markdown"] = lambda text: md.markdown(text) if text else ""


@router.post("/chat")
async def chat_endpoint(request: Request, message: str = Form(...)) -> Response:  # type: ignore
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    try:
        service = ChatService()
        result = await service.process_message(message)

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
        service = ChatService()
        raw_bytes = await file.read()
        result = await service.process_cv(raw_bytes, filename=file.filename or "unknown")

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
