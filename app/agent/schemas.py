from typing import Any

from pydantic import BaseModel, Field


class JobSpecialistInput(BaseModel):
    """Input for the Job Specialist Agent."""

    mode: str = Field(..., description="'search' or 'inspect'")
    query: str | None = Field(None, description="Search keywords (mode='search')")
    location: str | None = Field(None, description="Location (mode='search')")
    country: str = Field(default="gb", description="The country code (e.g., 'gb') (mode='search')")
    results_per_page: int = Field(default=10, description="Number of results to return (mode='search')")
    sort_by: str | None = Field(default=None, description="Sort by 'date' or 'salary' (mode='search')")
    max_days_old: int | None = Field(default=None, description="Filter jobs posted within these many days (mode='search')")
    salary_min: int | None = Field(default=None, description="Minimum salary (mode='search')")
    full_time: bool | None = Field(default=None, description="Filter for full-time jobs (mode='search')")
    part_time: bool | None = Field(default=None, description="Filter for part-time jobs (mode='search')")
    permanent: bool | None = Field(default=None, description="Filter for permanent jobs (mode='search')")
    contract: bool | None = Field(default=None, description="Filter for contract jobs (mode='search')")
    url: str | None = Field(None, description="Job URL (mode='inspect')")
    summary_context: dict[str, Any] | None = Field(None, description="JobSummary dict passed from Main Agent for context (mode='inspect')")


class JobListing(BaseModel):
    """Single source of truth for a job listing."""

    id: str = Field(default="", description="Deterministic hash for frontend tracking. Computed in _parse_agent_result, not by the LLM.")
    title: str = Field(..., description="The job title.")
    company: str = Field(..., description="The name of the company.")
    location: str = Field(..., description="The job location.")
    salary: str | None = Field(None, description="The salary range or amount. May contain '(Predicted)' for AI estimates.")
    description: str = Field(..., description="A brief summary of the job.")
    full_description: str | None = Field(None, description="The full job description text. Truncated to 1,000 characters.")
    apply_link: str = Field(..., description="The URL to apply for the job.")


class AgentResponse(BaseModel):
    """The structured response from the agent."""

    text_response: str = Field(..., description="The conversational response to the user.")
    jobs: list[JobListing] | None = Field(default=[], description="A list of job listings found, if any.")
