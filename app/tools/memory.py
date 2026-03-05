from typing import Annotated, Literal

import structlog
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedStore
from langgraph.store.base import BaseStore

from app.agent.memory_schema import Preference, UserProfile

logger = structlog.get_logger(__name__)


@tool
async def update_my_profile(
    config: RunnableConfig,
    store: Annotated[BaseStore, InjectedStore],
    name: Annotated[str | None, "Your name"] = None,
    role: Annotated[str | None, "Your current or desired job title"] = None,
    cv_summary: Annotated[str | None, "Comprehensive text summary of the CV (skills, experience, etc)"] = None,
) -> str:
    """
    Update your core profile information (Name, Role, CV Summary).
    Use this when the user explicitly tells you who they are or what they do.
    Also use this to store the structured CV analysis after processing a CV.
    Example: User says "I am a Senior Python Dev", call update_my_profile(role="Senior Python Dev").

    cv_summary is now a single string containing the full analysis.
    """
    try:
        user_id = config.get("configurable", {}).get("user_id", "default_user")
        namespace = (user_id, "profile")

        logger.info("Tool Started: update_my_profile", name=name, role=role, has_cv=bool(cv_summary))

        existing = await store.aget(namespace, "data")
        if existing:
            profile = UserProfile(**existing.value)
        else:
            profile = UserProfile()

        if name:
            profile.name = name
        if role:
            profile.role = role
        if cv_summary:
            profile.cv_summary = cv_summary
            profile.cv_uploaded = True

        await store.aput(namespace, "data", profile.model_dump())
        logger.info("Tool Completed: update_my_profile", success=True)
        return f"Profile updated successfully: {profile.model_dump()}"
    except Exception as e:
        logger.error("Failed to update profile", exc_info=True)
        return f"Error updating profile: {str(e)}"


@tool
async def save_preference(
    config: RunnableConfig,
    store: Annotated[BaseStore, InjectedStore],
    key: Annotated[
        str, "A short machine identifier for this preference, e.g. 'min_salary', 'remote', 'tech_stack'. Used for deduplication and deletion."
    ],
    label: Annotated[str, "A human-readable sentence describing the preference, e.g. 'Min salary £100k', 'Remote only', 'No agencies'."],
    sentiment: Annotated[
        Literal["positive", "negative"], "Use 'positive' when user wants something, 'negative' when they want to avoid it."
    ] = "positive",
) -> str:
    """
    Save a user preference or constraint.
    Example: User says "I only want remote jobs" → save_preference(key="remote", label="Remote only", sentiment="positive")
    Example: User says "No agencies" → save_preference(key="agencies", label="No agencies", sentiment="negative")
    Example: User says "Min £80k salary" → save_preference(key="min_salary", label="Min salary £80k", sentiment="positive")
    """
    try:
        user_id = config.get("configurable", {}).get("user_id", "default_user")
        namespace = (user_id, "preferences")

        logger.info("Tool Started: save_preference", key=key, label=label, sentiment=sentiment)

        pref = Preference(key=key, label=label, sentiment=sentiment)
        await store.aput(namespace, key, pref.model_dump())

        return f"Preference saved: {key} = {label} ({sentiment})"
    except Exception as e:
        logger.error("Failed to save preference", exc_info=True, extra={"preference_key": key})
        return f"Error saving preference: {str(e)}"


@tool
async def delete_preference(
    config: RunnableConfig,
    store: Annotated[BaseStore, InjectedStore],
    key: Annotated[str, "The preference key to remove"],
) -> str:
    """
    Remove a preference that is no longer valid.
    Example: User says "Actually, I'm okay with onsite work now", call delete_preference("location").
    """
    try:
        user_id = config.get("configurable", {}).get("user_id", "default_user")
        namespace = (user_id, "preferences")

        logger.info("Tool Started: delete_preference", key=key)

        # Check if exists first to match legacy behavior
        existing = await store.aget(namespace, key)
        if not existing:
            return f"Preference '{key}' not found."

        await store.adelete(namespace, key)
        logger.info("Tool Completed: delete_preference", key=key)
        return f"Preference '{key}' deleted."
    except Exception as e:
        logger.error("Failed to delete preference", exc_info=True, extra={"preference_key": key})
        return f"Error deleting preference: {str(e)}"


@tool
async def finalize_profile(
    config: RunnableConfig,
    store: Annotated[BaseStore, InjectedStore],
) -> str:
    """
    Signal that onboarding is complete and hand off to the main job-hunting agent.
    Call this ONLY after you have gathered enough information about the user
    via update_my_profile and save_preference.
    """
    try:
        user_id = config.get("configurable", {}).get("user_id", "default_user")
        namespace = (user_id, "profile")

        logger.info("Tool Started: finalize_profile")

        # Verify profile has minimum data before finalizing
        existing = await store.aget(namespace, "data")
        profile = UserProfile(**existing.value) if existing else UserProfile()

        if not profile.name and not profile.role:
            return "Cannot finalize: please set at least a name or role first."

        # Persist the onboarding_complete flag in the store
        await store.aput((user_id, "onboarding"), "status", {"onboarding_complete": True})

        return "Onboarding complete — handing off to job hunting agent."
    except Exception as e:
        logger.error("Failed to finalize profile", exc_info=True)
        return f"Error finalizing profile: {str(e)}"
