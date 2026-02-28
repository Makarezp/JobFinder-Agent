from typing import Literal

from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    """
    Core identity of the user. Only contains explicit facts.
    """

    id: int = 1
    name: str | None = None
    role: str | None = Field(default=None, description="Current job title, e.g. 'Senior Backend Engineer'")
    cv_summary: str | None = Field(default=None, description="Detailed text summary of the CV (experience, skills, etc).")
    cv_uploaded: bool = Field(default=False, description="Whether a CV has been uploaded")


class Preference(BaseModel):
    """
    A specific constraint or preference for job searching.
    """

    key: str = Field(..., description="Machine identifier used as store key and for delete routing, e.g. 'min_salary', 'remote'")
    label: str = Field(..., description="Human-readable display sentence, e.g. 'Min salary £100k', 'Remote only', 'No agencies'")
    sentiment: Literal["positive", "negative"] = Field("positive", description="'positive' = wants it, 'negative' = wants to avoid it")


class PendingJob(BaseModel):
    """
    A job card returned by the agent, pending a pass/pursue decision.
    Stored under (user_id, "pending_jobs") namespace in the LangGraph memory store.
    Mirrors the frontend Job interface exactly, plus store-level metadata.
    """

    id: str
    title: str
    company: str
    location: str
    salary: str | None = None
    description: str
    full_description: str | None = None
    apply_link: str
    added_at: str  # ISO 8601 format — store metadata, not exposed to frontend


class DecisionLog(BaseModel):
    """
    Records a user's pass/pursue decision on a specific job card.
    Stored under (user_id, "decisions") namespace in the LangGraph memory store.
    """

    job_title: str
    company: str
    action: Literal["pass", "pursue"]
    reason: str | None = None
    timestamp: str  # ISO 8601 format, e.g. "2026-02-22T20:32:00+00:00"
