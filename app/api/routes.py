import logging
import traceback
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from langgraph.store.base import BaseStore

from app.agent.constants import DEFAULT_USER_ID
from app.agent.memory_schema import Preference, UserProfile
from app.api.dependencies import get_admin_service, get_chat_service, get_store
from app.api.schemas import ChatRequest
from app.services.admin_service import AdminService
from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

# Type aliases for injected dependencies
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
StoreDep = Annotated[BaseStore, Depends(get_store)]
AdminServiceDep = Annotated[AdminService, Depends(get_admin_service)]


@router.get("/profile")
async def profile_page(store: StoreDep) -> JSONResponse:
    """Return the user profile and preferences as JSON."""
    user_id = DEFAULT_USER_ID

    # Fetch Profile
    profile_item = await store.aget((user_id, "profile"), "data")
    profile = UserProfile(**profile_item.value) if profile_item else UserProfile()

    # Fetch Preferences
    prefs_items = await store.asearch((user_id, "preferences"))
    preferences: dict[str, object] = {}
    for item in prefs_items:
        if item.value:
            try:
                pref = Preference(**item.value)
                preferences[item.key] = pref.model_dump()
            except Exception:
                preferences[item.key] = item.value

    return JSONResponse(content={"profile": profile.model_dump(), "preferences": preferences})


@router.delete("/profile/reset")
async def reset_profile(admin_service: AdminServiceDep) -> JSONResponse:
    """Hard reset of the application state."""
    await admin_service.reset_system()
    return JSONResponse(content={"status": "ok"})


@router.post("/chat")
async def chat_endpoint(body: ChatRequest, service: ChatServiceDep) -> JSONResponse:
    if not body.message:
        raise HTTPException(status_code=400, detail="Message is required")

    try:
        result = await service.process_message(body.message)
        return JSONResponse(content=result)

    except Exception as e:
        logger.error("Error processing chat request: %s\n%s", str(e), traceback.format_exc())
        return JSONResponse(
            status_code=200,
            content={
                "user_message": body.message,
                "ai_message": f"**System Error**: {str(e)}",
                "jobs": [],
            },
        )


@router.post("/upload-cv")
async def upload_cv(service: ChatServiceDep, file: UploadFile = File(...)) -> JSONResponse:
    try:
        raw_bytes = await file.read()
        result = await service.process_cv(raw_bytes, filename=file.filename or "unknown")
        return JSONResponse(content=result)

    except Exception as e:
        logger.error("Error processing CV upload: %s\n%s", str(e), traceback.format_exc())
        return JSONResponse(
            status_code=200,
            content={
                "user_message": "CV Upload Failed",
                "ai_message": f"**System Error**: {str(e)}",
                "jobs": [],
            },
        )


@router.get("/history")
async def get_history(service: ChatServiceDep) -> JSONResponse:
    """Return the chat history as a JSON array."""
    history = await service.get_history()
    return JSONResponse(content=history)
