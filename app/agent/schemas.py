from pydantic import BaseModel, Field


class JobSpecialistInput(BaseModel):
    """Input for the Job Specialist Agent."""

    query: str = Field(
        ...,
        description=(
            "A single, simple job title or role keyword. "
            "DO NOT use Boolean operators ('or', 'and', '|'). "
            "DO NOT combine multiple job titles in one query. "
            "You MUST include the exact location at the end of the query string, especially outside the US. "
            "GOOD: 'admin assistant London', 'social media coordinator UK'. "
            "BAD: 'admin or social media or customer service', 'receptionist'."
        ),
    )
    date_posted: str = Field(default="all", description="Filter by posting date. One of: 'all', 'today', '3days', 'week', 'month'.")
    employment_types: str | None = Field(default=None, description="Comma-separated employment types: FULLTIME, CONTRACTOR, PARTTIME, INTERN.")
    remote_only: bool = Field(default=False, description="Restrict results to remote-only positions.")
    page: int = Field(default=1, description="Page number for pagination.")


class JobListing(BaseModel):
    """Single source of truth for a job listing."""

    id: str = Field(default="", description="Unique identifier for frontend tracking.")
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
    jobs: list[JobListing] = Field(default=[], description="A list of job listings found, if any.")
