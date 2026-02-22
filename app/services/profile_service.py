from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

import structlog
from langgraph.store.base import BaseStore

from app.agent.constants import DEFAULT_USER_ID
from app.agent.memory_schema import DecisionLog, Preference, UserProfile

logger = structlog.get_logger(__name__)


class ProfileService:
    def __init__(self, store: BaseStore) -> None:
        self._store = store

    async def get_profile_data(self, user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
        """Fetch profile, preferences, and decision log from the store."""
        # Fetch Profile
        profile_item = await self._store.aget((user_id, "profile"), "data")
        profile = UserProfile(**profile_item.value) if profile_item else UserProfile()

        # Fetch Preferences
        prefs_items = await self._store.asearch((user_id, "preferences"))
        preferences: dict[str, Any] = {}
        for item in prefs_items:
            if item.value:
                try:
                    pref = Preference(**item.value)
                    preferences[item.key] = pref.model_dump()
                except Exception:
                    preferences[item.key] = item.value

        # Fetch Decisions (sorted most recent first)
        decisions_items = await self._store.asearch((user_id, "decisions"))
        decisions = sorted(
            [DecisionLog(**item.value).model_dump() for item in decisions_items if item.value],
            key=lambda d: d["timestamp"],
            reverse=True,
        )

        return {
            "profile": profile.model_dump(),
            "preferences": preferences,
            "decisions": decisions,
        }

    async def log_decision(
        self,
        job_title: str,
        company: str,
        action: Literal["pass", "pursue"],
        description: str | None,
        reason: str | None,
        user_id: str = DEFAULT_USER_ID,
    ) -> None:
        """Persist a pass/pursue decision to the store under (user_id, 'decisions')."""
        key = str(uuid4())
        log = DecisionLog(
            job_title=job_title,
            company=company,
            action=action,
            description=description,
            reason=reason,
            timestamp=datetime.now(UTC).isoformat(),
        )
        await self._store.aput((user_id, "decisions"), key, log.model_dump())
        logger.info("Decision logged", job_title=job_title, company=company, action=action)
