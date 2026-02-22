from typing import Any, Literal

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

    key: str = Field(..., description="The setting name, e.g. 'min_salary', 'remote', 'tech_stack'")
    value: Any = Field(..., description="The value. Can be string, int, list, or boolean.")
    category: Literal["hard", "soft"] = Field("soft", description="'hard' for strict filters (must have), 'soft' for preferences (nice to have)")
    sentiment: Literal["positive", "negative"] = Field("positive", description="'positive' for things the user wants, 'negative' for things to avoid")


class DecisionLog(BaseModel):
    """
    Records a user's pass/pursue decision on a specific job card.
    Stored under (user_id, "decisions") namespace in the LangGraph memory store.
    """

    job_title: str
    company: str
    action: Literal["pass", "pursue"]
    description: str | None = None
    reason: str | None = None
    timestamp: str  # ISO 8601 format, e.g. "2026-02-22T20:32:00+00:00"
