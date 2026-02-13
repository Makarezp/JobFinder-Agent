from typing import List, Optional
from pydantic import BaseModel, Field


class JobListing(BaseModel):
    """Represents a single job listing."""

    title: str = Field(..., description="The job title.")
    company: str = Field(..., description="The name of the company.")
    location: str = Field(..., description="The job location.")
    salary: Optional[str] = Field(
        None, description="The salary range or amount, if available."
    )
    description: str = Field(..., description="A brief summary of the job.")
    apply_link: str = Field(..., description="The URL to apply for the job.")


class AgentResponse(BaseModel):
    """The structured response from the agent."""

    text_response: str = Field(
        ..., description="The conversational response to the user."
    )
    jobs: Optional[List[JobListing]] = Field(
        default=[], description="A list of job listings found, if any."
    )
