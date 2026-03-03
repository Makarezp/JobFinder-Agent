from pydantic import BaseModel, Field


class JobSpecialistInput(BaseModel):
    """Input for the Job Specialist Agent."""

    query: str = Field(
        ...,
        description=(
            "A single, simple job title or role keyword. "
            "DO NOT use Boolean operators ('or', 'and', '|'). "
            "DO NOT combine multiple job titles in one query. "
            "DO NOT include the location in this field — location belongs at the end of the query string only if JSearch requires it. "
            "GOOD: 'admin assistant', 'social media coordinator', 'receptionist'. "
            "BAD: 'admin or social media or customer service', 'part time admin or receptionist in St Albans'."
        ),
    )
    date_posted: str = Field(default="all", description="Filter by posting date. One of: 'all', 'today', '3days', 'week', 'month'.")
    employment_types: str | None = Field(default=None, description="Comma-separated employment types: FULLTIME, CONTRACTOR, PARTTIME, INTERN.")
    country: str = Field(
        default="us",
        description="2-letter ISO 3166-1 alpha-2 country code (e.g., 'us', 'gb', 'de'). Infer this from the user's location.",
    )
    remote_only: bool = Field(default=False, description="Restrict results to remote-only positions.")
    page: int = Field(default=1, description="Page number for pagination.")


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
