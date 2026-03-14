from typing import Any, NotRequired, TypedDict

from app.agent.schemas import JobListing, JobSpecialistInput


class JobSpecialistState(TypedDict):
    """
    State for the Job Search Specialist subgraph.
    """

    input: JobSpecialistInput
    user_profile: dict[str, Any] | None
    preferences: dict[str, Any] | None
    search_results: list[JobListing] | None
    summaries: NotRequired[list[dict[str, Any]]]
    job_payloads: NotRequired[list[dict[str, Any]]]
    tool_message_content: NotRequired[str]
