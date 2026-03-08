import asyncio
from typing import Any

import structlog
from langchain_core.runnables import RunnableConfig
from langgraph.store.base import BaseStore

from app.agent.memory_schema import Preference, UserProfile
from app.agent.profile.state import ProfileAgentState

logger = structlog.get_logger(__name__)


async def fetch_profile_data(
    state: ProfileAgentState,
    config: RunnableConfig,
    store: BaseStore,
) -> dict[str, Any]:
    """Read user profile and preferences from Store and inject into state."""
    logger.info("Node Started: fetch_profile_data")
    user_id = config.get("configurable", {}).get("user_id", "default_user")

    profile_item, prefs_items = await asyncio.gather(
        store.aget((user_id, "profile"), "data"),
        store.asearch((user_id, "preferences")),
    )

    profile = UserProfile(**profile_item.value) if profile_item else UserProfile()

    preferences: dict[str, Any] = {}
    for item in prefs_items:
        if item.value:
            try:
                pref = Preference(**item.value)
                preferences[item.key] = pref.model_dump()
            except Exception:
                logger.warning("Skipping invalid preference", key=item.key)

    logger.info(
        "Node Completed: fetch_profile_data",
        profile=profile.model_dump(),
        pref_count=len(preferences),
    )
    return {
        "user_profile": profile.model_dump(),
        "preferences": preferences,
    }
