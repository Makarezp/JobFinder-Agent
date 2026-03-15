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


class SeenJob(BaseModel):
    """
    Minimal identity record for a job that has already been processed by the LLM.
    Stored under (user_id, "seen_jobs") namespace in the LangGraph memory store.
    Only 4 fields — deliberately excludes description, salary, apply_link to
    minimise token cost when seen jobs appear in ToolMessage payloads.
    """

    id: str
    title: str
    company: str
    location: str


class SearchLedgerEntry(BaseModel):
    """Record of a single job search execution.
    Stored under (user_id, 'search_ledger') namespace in the LangGraph Store.
    The LLM reads these entries to avoid repeating searches and to discover
    unexplored pages.
    """

    query: str = Field(..., description="Raw query string passed to JSearch (e.g., 'Python Developer in London')")
    country: str = Field(..., description="2-letter ISO country code used in the search")
    remote_only: bool = Field(default=False, description="Whether remote_only filter was applied")
    page: int = Field(..., description="Page number that was fetched")
    results_count: int = Field(..., description="Total number of jobs returned by the API for this page")
    fresh_count: int = Field(..., description="Number of jobs that were new (not previously seen)")
    has_more: bool = Field(..., description="True if results_count >= expected page size, indicating more pages exist")
    searched_at: str = Field(..., description="ISO 8601 timestamp of when this search was executed")
