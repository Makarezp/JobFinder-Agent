"""
Constants for the Agent module.
"""

from typing import Final

# Tool Names
FINAL_ANSWER_TOOL_NAME: Final[str] = "final_answer"

# Protocol Keys (Agent Response)
TEXT_RESPONSE_KEY: Final[str] = "text_response"
JOBS_KEY: Final[str] = "jobs"

# State Keys
MESSAGES_KEY: Final[str] = "messages"
CV_RAW_TEXT_KEY: Final[str] = "cv_raw_text"

# Default Thread
DEFAULT_THREAD_ID: Final[str] = "default_user_session"
DEFAULT_USER_ID: Final[str] = "default_user"

# Search Limits
MAX_SEARCH_ATTEMPTS: Final[int] = 5

# Node Names
ONBOARDING_CHATBOT_NODE: Final[str] = "onboarding_chatbot"
ONBOARDING_TOOLS_NODE: Final[str] = "onboarding_tools"

# Profile Agent Node Names
PROFILE_FETCH_NODE: Final[str] = "fetch_profile_data"
PROFILE_CHATBOT_NODE: Final[str] = "profile_chatbot"
PROFILE_TOOLS_NODE: Final[str] = "profile_tools"

# Discovery Agent Node Names
DISCOVERY_FETCH_PROFILE_NODE: Final[str] = "fetch_profile"
DISCOVERY_CHATBOT_NODE: Final[str] = "discovery_chatbot"
DISCOVERY_TOOLS_NODE: Final[str] = "discovery_tools"
DISCOVERY_JOB_SPECIALIST_NODE: Final[str] = "job_specialist_node"

# Job Specialist Pipeline
SUMMARY_BATCH_SIZE: Final[int] = 4
SUMMARY_LLM_TIMEOUT: Final[float] = 60.0
