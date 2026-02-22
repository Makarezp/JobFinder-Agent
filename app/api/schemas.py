from typing import Literal

from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str


class FeedbackRequest(BaseModel):
    job_title: str
    company: str
    action: Literal["pass", "pursue"]
    description: str | None = None
    reason: str | None = None
