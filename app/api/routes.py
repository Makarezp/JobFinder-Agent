from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from app.agent.constants import DEFAULT_USER_ID
from app.api.dependencies import get_admin_service, get_chat_service, get_profile_service
from app.api.schemas import ChatRequest, DeckResponse, FeedbackRequest
from app.services.admin_service import AdminService
from app.services.chat_service import ChatService
from app.services.profile_service import ProfileService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api")

# Type aliases for injected dependencies
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
ProfileServiceDep = Annotated[ProfileService, Depends(get_profile_service)]
AdminServiceDep = Annotated[AdminService, Depends(get_admin_service)]


@router.get("/deck")
async def get_deck(service: ProfileServiceDep) -> DeckResponse:
    """Return the user's current pending job deck."""
    jobs = await service.get_pending_jobs(DEFAULT_USER_ID)
    return DeckResponse(jobs=jobs)


@router.get("/profile")
async def profile_page(service: ProfileServiceDep) -> JSONResponse:
    """Return the user profile, preferences, and decision log as JSON."""
    data = await service.get_profile_data(DEFAULT_USER_ID)
    return JSONResponse(content=data)


@router.post("/feedback")
async def submit_feedback(body: FeedbackRequest, service: ProfileServiceDep) -> JSONResponse:
    """Log a user's pass/pursue decision on a job card to the memory store."""
    await service.log_decision(
        job_title=body.job_title,
        company=body.company,
        action=body.action,
        reason=body.reason,
        user_id=DEFAULT_USER_ID,
    )
    await service.remove_pending_job(body.job_id, DEFAULT_USER_ID)
    return JSONResponse(content={"status": "ok"})


@router.delete("/profile/reset")
async def reset_profile(admin_service: AdminServiceDep) -> JSONResponse:
    """Hard reset of the application state."""
    await admin_service.reset_system()
    return JSONResponse(content={"status": "ok"})


@router.delete("/profile/reset-discovery")
async def reset_discovery(admin_service: AdminServiceDep) -> JSONResponse:
    """Reset only the discovery graph state, preserving the user's profile."""
    await admin_service.reset_discovery(DEFAULT_USER_ID)
    return JSONResponse(content={"status": "ok"})


@router.post("/chat")
async def chat_endpoint(body: ChatRequest, service: ChatServiceDep) -> JSONResponse:
    if not body.message:
        raise HTTPException(status_code=400, detail="Message is required")

    try:
        result = await service.process_message(body.message, workspace=body.workspace)
        return JSONResponse(content=result)

    except Exception as e:
        logger.exception("Error processing chat request", error=str(e))
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
        logger.exception("Error processing CV upload", error=str(e))
        return JSONResponse(
            status_code=200,
            content={
                "user_message": "CV Upload Failed",
                "ai_message": f"**System Error**: {str(e)}",
                "jobs": [],
            },
        )


@router.get("/history")
async def get_history(
    service: ChatServiceDep,
    workspace: Literal["discovery", "profile"] = Query(default="discovery"),
) -> JSONResponse:
    """Return the chat history as a JSON array."""
    history = await service.get_history(workspace=workspace)
    return JSONResponse(content=history)
