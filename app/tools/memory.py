from typing import Annotated, Any, Literal

from langchain_core.tools import tool

from app.core.database import (
    delete_preference as db_delete_preference,
)
from app.core.database import (
    save_preference as db_save_preference,
)
from app.core.database import (
    update_profile as db_update_profile,
)


@tool
def update_my_profile(
    name: Annotated[str | None, "Your name"] = None,
    role: Annotated[str | None, "Your current or desired job title"] = None,
) -> str:
    """
    Update your core profile information (Name, Role).
    Use this when the user explicitly tells you who they are or what they do.
    Example: User says "I am a Senior Python Dev", call update_my_profile(role="Senior Python Dev").
    """
    try:
        updated = db_update_profile(name=name, role=role)
        return f"Profile updated successfully: {updated}"
    except Exception as e:
        return f"Error updating profile: {str(e)}"


@tool
def save_preference(
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
        # DB handles JSON serialization
        db_save_preference(key, value, category)
        return f"Preference saved: {key} = {value} ({category})"
    except Exception as e:
        return f"Error saving preference: {str(e)}"


@tool
def delete_preference(
    key: Annotated[str, "The preference key to remove"],
) -> str:
    """
    Remove a preference that is no longer valid.
    Example: User says "Actually, I'm okay with onsite work now", call delete_preference("location").
    """
    try:
        if db_delete_preference(key):
            return f"Preference '{key}' deleted."
        return f"Preference '{key}' not found."
    except Exception as e:
        return f"Error deleting preference: {str(e)}"
