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
ONBOARDING_COMPLETE_KEY: Final[str] = "onboarding_complete"

# Default Thread
DEFAULT_THREAD_ID: Final[str] = "default_user_session"
DEFAULT_USER_ID: Final[str] = "default_user"

# Node Names
ROUTER_NODE: Final[str] = "router"
CHECK_ONBOARDING_NODE: Final[str] = "check_onboarding_status"
ONBOARDING_CHATBOT_NODE: Final[str] = "onboarding_chatbot"
ONBOARDING_TOOLS_NODE: Final[str] = "onboarding_tools"
FETCH_PROFILE_NODE: Final[str] = "fetch_profile"
MAIN_CHATBOT_NODE: Final[str] = "main_chatbot"
MAIN_TOOLS_NODE: Final[str] = "main_tools"
JOB_SPECIALIST_NODE: Final[str] = "job_specialist_node"
