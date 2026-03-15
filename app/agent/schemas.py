from pydantic import BaseModel, Field


class JobSpecialistInput(BaseModel):
    """Input for the Job Specialist Agent."""

    query: str = Field(
        ...,
        description=(
            "A job title or role keyword, optionally including location and employment type. "
            "Use the format '[Role] in [Location]'. "
            "NEVER include salary numbers (like '100k' or 'high salary') in the query string, as this "
            "causes JSearch to return 0 results or miss jobs with hidden salaries. "
            "Instead, if a user wants a high salary, search for higher seniority titles like 'Lead', 'Principal', or 'Staff'. "
            "Include semantic keywords like 'contract', 'part-time', or 'permanent' directly in the query string. "
            "DO NOT use Boolean operators ('or', 'and', '|'). "
            "GOOD: 'Android Developer in London', 'Staff Android Developer UK'."
        ),
    )
    country: str = Field(
        ...,
        description=(
            "2-letter ISO 3166-1 alpha-2 country code (e.g., 'us', 'gb', 'de'). MANDATORY. Infer this from the user's location, CV, or preferences."
        ),
    )
    date_posted: str = Field(
        default="month",
        description=(
            "Filter by posting date. One of: 'all', 'today', '3days', 'week', 'month'. "
            "Defaults to 'month' to avoid missing high-quality roles posted just outside a 7-day window."
        ),
    )
    remote_only: bool = Field(default=False, description="Restrict results to remote-only positions.")
    page: int = Field(default=1, description="Page number for pagination. Increment this if you need to fetch more results for the same query.")
    num_pages: int = Field(default=2, description="Number of pages to return per search call (max 20). Defaults to 2 to get up to 20 jobs at once.")


class JobListing(BaseModel):
    """Single source of truth for a job listing."""

    id: str = Field(default="", description="Unique identifier for frontend tracking.")
    title: str = Field(..., description="The job title.")
    company: str = Field(..., description="The name of the company.")
    location: str = Field(..., description="The job location.")
    salary: str | None = Field(None, description="The salary range or amount. May contain '(Predicted)' for AI estimates.")
    description: str = Field(..., description="A brief summary of the job.")
    full_description: str | None = Field(None, description="The full job description text. Truncated to 5,000 characters.")
    apply_link: str = Field(..., description="The URL to apply for the job.")


class AgentResponse(BaseModel):
    """The structured response from the agent."""

    text_response: str = Field(..., description="The conversational response to the user.")
    selected_job_indexes: list[int] = Field(
        default=[],
        description=("1-based indexes of jobs from job_specialist_tool results to present to the user."),
    )


class JobSummary(BaseModel):
    """Single job summary result from the LLM."""

    model_config = {"extra": "forbid"}

    job_id: str = Field(..., description="The id of the summarized JobListing.")
    description: str = Field(
        ...,
        description=(
            "A ~500-character profile-aware analytical summary covering Essence, Conditions, and Limitations. This replaces the raw JSearch snippet."
        ),
    )


class JobSummaryBatch(BaseModel):
    """Structured output schema enforced on the summary LLM via with_structured_output."""

    summaries: list[JobSummary] = Field(..., description="One summary per job in the input batch.")
