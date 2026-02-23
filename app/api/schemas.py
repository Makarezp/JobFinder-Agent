from typing import Literal

from pydantic import BaseModel

from app.agent.memory_schema import PendingJob


class ChatRequest(BaseModel):
    message: str


class FeedbackRequest(BaseModel):
    job_title: str
    company: str
    action: Literal["pass", "pursue"]
    description: str | None = None
    reason: str | None = None
    job_id: str


class DeckResponse(BaseModel):
    jobs: list[PendingJob]
