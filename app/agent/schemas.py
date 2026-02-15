from typing import Any

from pydantic import BaseModel, Field


class JobSpecialistInput(BaseModel):
    """Input for the Job Specialist Agent."""

    mode: str = Field(..., description="'search' or 'inspect'")
    query: str | None = Field(None, description="Search keywords (mode='search')")
    location: str | None = Field(None, description="Location (mode='search')")
    url: str | None = Field(None, description="Job URL (mode='inspect')")
    summary_context: dict[str, Any] | None = Field(None, description="JobSummary dict passed from Main Agent for context (mode='inspect')")


class JobSummary(BaseModel):
    """Lightweight job summary for list views."""

    id: str = Field(..., description="Unique identifier or URL hash.")
    title: str = Field(..., description="The job title.")
    company: str = Field(..., description="The name of the company.")
    location: str = Field(..., description="The job location.")
    salary: str = Field(default="Negotiable", description="The salary range or amount.")
    snippet: str = Field(..., description="A very brief snippet/preview of the description.")
    url: str = Field(..., description="The URL to apply or view details.")
    created: str | None = Field(None, description="Date posted.")


class JobDetail(BaseModel):
    """Detailed job information including full description."""

    summary: JobSummary
    full_description: str = Field(..., description="The full job description text.")
    requirements: list[str] | None = Field(default=None, description="Extracted requirements.")
    benefits: list[str] | None = Field(default=None, description="Extracted benefits.")


class JobListing(BaseModel):
    """Represents a single job listing (Legacy/Main Agent compatibility)."""

    title: str = Field(..., description="The job title.")
    company: str = Field(..., description="The name of the company.")
    location: str = Field(..., description="The job location.")
    salary: str | None = Field(None, description="The salary range or amount, if available.")
    description: str = Field(..., description="A brief summary of the job.")
    apply_link: str = Field(..., description="The URL to apply for the job.")


class AgentResponse(BaseModel):
    """The structured response from the agent."""

    text_response: str = Field(..., description="The conversational response to the user.")
    jobs: list[JobListing] | None = Field(default=[], description="A list of job listings found, if any.")
