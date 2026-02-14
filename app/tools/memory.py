import logging
from typing import Annotated, Any, Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedStore
from langgraph.store.base import BaseStore

from app.agent.memory_schema import Preference, UserProfile

logger = logging.getLogger(__name__)


@tool
def update_my_profile(
    config: RunnableConfig,
    store: Annotated[BaseStore, InjectedStore],
    name: Annotated[str | None, "Your name"] = None,
    role: Annotated[str | None, "Your current or desired job title"] = None,
) -> str:
    """
    Update your core profile information (Name, Role).
    Use this when the user explicitly tells you who they are or what they do.
    Example: User says "I am a Senior Python Dev", call update_my_profile(role="Senior Python Dev").
    """
    try:
        user_id = config.get("configurable", {}).get("user_id", "default_user")
        namespace = (user_id, "profile")

        # Get existing profile to merge updates
        existing = store.get(namespace, "data")
        # Load into Pydantic model
        profile = UserProfile(**existing.value) if existing else UserProfile()

        if name:
            profile.name = name
        if role:
            profile.role = role

        store.put(namespace, "data", profile.model_dump())
        return f"Profile updated successfully: {profile.model_dump()}"
    except Exception as e:
        logger.error("Failed to update profile", exc_info=True)
        return f"Error updating profile: {str(e)}"


@tool
def save_preference(
    config: RunnableConfig,
    store: Annotated[BaseStore, InjectedStore],
    key: Annotated[str, "The preference key (e.g., 'min_salary', 'location', 'tech_stack')"],
    value: Annotated[Any, "The value (string, number, boolean, or list)"],
    category: Annotated[
        Literal["hard", "soft"], "Is this a strict requirement ('hard') or just nice to have ('soft')?"
    ] = "soft",
) -> str:
    """
    Save a user preference or constraint.
    - Hard constraints: strict filters (e.g., "Remote only", "Min $100k").
    - Soft preferences: vibe checks (e.g., "I like startups", "No fintech").

    Example: User says "I only want remote jobs", call save_preference("location", "Remote", "hard").
    """
    try:
        user_id = config.get("configurable", {}).get("user_id", "default_user")
        namespace = (user_id, "preferences")

        # Use Pydantic model for validation
        pref = Preference(key=key, value=value, category=category)

        # Store using model_dump
        store.put(namespace, key, pref.model_dump())

        return f"Preference saved: {key} = {value} ({category})"
    except Exception as e:
        logger.error("Failed to save preference", exc_info=True, extra={"preference_key": key, "category": category})
        return f"Error saving preference: {str(e)}"


@tool
def delete_preference(
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

        # Check if exists first to match legacy behavior
        existing = store.get(namespace, key)
        if not existing:
            return f"Preference '{key}' not found."

        store.delete(namespace, key)
        return f"Preference '{key}' deleted."
    except Exception as e:
        logger.error("Failed to delete preference", exc_info=True, extra={"preference_key": key})
        return f"Error deleting preference: {str(e)}"
