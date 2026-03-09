from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

import structlog
from langgraph.store.base import BaseStore

from app.agent.constants import DEFAULT_USER_ID
from app.agent.memory_schema import DecisionLog, PendingJob, Preference, SeenJob, UserProfile
from app.agent.schemas import JobListing

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
        reason: str | None,
        user_id: str = DEFAULT_USER_ID,
    ) -> None:
        """Persist a pass/pursue decision to the store under (user_id, 'decisions')."""
        key = str(uuid4())
        log = DecisionLog(
            job_title=job_title,
            company=company,
            action=action,
            reason=reason,
            timestamp=datetime.now(UTC).isoformat(),
        )
        await self._store.aput((user_id, "decisions"), key, log.model_dump())
        logger.info("Decision logged", job_title=job_title, company=company, action=action)

    async def get_pending_jobs(self, user_id: str = DEFAULT_USER_ID) -> list[PendingJob]:
        """Fetch all non-removed pending jobs from the store under (user_id, 'pending_jobs')."""
        logger.info("Fetching pending jobs", user_id=user_id)
        items = await self._store.asearch((user_id, "pending_jobs"))
        jobs = [PendingJob(**item.value) for item in items if item.value and not item.value.get("removed")]
        logger.info("Pending jobs fetched", user_id=user_id, count=len(jobs))
        return jobs

    async def add_pending_jobs(self, jobs: list[dict[str, Any]], user_id: str = DEFAULT_USER_ID) -> None:
        """Persist a list of jobs to the store, keyed by their deterministic id."""
        logger.info("Adding pending jobs", user_id=user_id, count=len(jobs))
        for job in jobs:
            pending = PendingJob(
                added_at=datetime.now(UTC).isoformat(),
                **job,
            )
            await self._store.aput((user_id, "pending_jobs"), pending.id, pending.model_dump())
        logger.info("Pending jobs added", user_id=user_id, count=len(jobs))

    async def remove_pending_job(self, job_id: str, user_id: str = DEFAULT_USER_ID) -> None:
        """Soft-delete a pending job by marking it removed: True."""
        logger.info("Removing pending job", user_id=user_id, job_id=job_id)
        await self._store.aput((user_id, "pending_jobs"), job_id, {"removed": True})
        logger.info("Pending job removed", user_id=user_id, job_id=job_id)

    async def get_seen_job_ids(self, user_id: str = DEFAULT_USER_ID) -> set[str]:
        """Return the set of all job IDs previously processed by the LLM."""
        items = await self._store.asearch((user_id, "seen_jobs"))
        return {item.key for item in items if item.value}

    async def reset_discovery_state(self, user_id: str = DEFAULT_USER_ID) -> None:
        """Delete all job-related store entries for a user: pending_jobs, seen_jobs, decisions."""
        logger.warning("Resetting discovery state.", user_id=user_id)
        for namespace_key in ("pending_jobs", "seen_jobs", "decisions"):
            namespace = (user_id, namespace_key)
            items = await self._store.asearch(namespace)
            for item in items:
                await self._store.adelete(namespace, item.key)
        logger.info("Discovery state reset complete.", user_id=user_id)

    async def mark_jobs_seen(
        self,
        jobs: list[JobListing],
        user_id: str = DEFAULT_USER_ID,
    ) -> None:
        """Persist minimal identity records for all jobs returned by a search."""
        for job in jobs:
            seen = SeenJob(id=job.id, title=job.title, company=job.company, location=job.location)
            await self._store.aput((user_id, "seen_jobs"), job.id, seen.model_dump())
