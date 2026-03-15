"""
Unit tests for ProfileService search ledger methods (Sprint V2, Ticket 1).

Covers:
- SearchLedgerEntry model validation
- log_search persists correct entries
- get_search_ledger returns sorted results
- reset_discovery_state clears search_ledger namespace
"""

from datetime import datetime

import pytest
from langgraph.store.memory import InMemoryStore
from pydantic import ValidationError

from app.agent.constants import DEFAULT_USER_ID, FETCH_NUM_PAGES
from app.agent.memory_schema import SearchLedgerEntry
from app.agent.schemas import JobSpecialistInput
from app.services.profile_service import ProfileService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_input(
    query: str = "Python Developer in London",
    country: str = "gb",
    page: int = 1,
    remote_only: bool = False,
) -> JobSpecialistInput:
    return JobSpecialistInput(query=query, country=country, page=page, remote_only=remote_only)


# ---------------------------------------------------------------------------
# SearchLedgerEntry model tests
# ---------------------------------------------------------------------------


def test_search_ledger_entry_validates() -> None:
    """Valid SearchLedgerEntry round-trips through model_dump / model_validate."""
    entry = SearchLedgerEntry(
        query="Python Developer in London",
        country="gb",
        remote_only=False,
        page=1,
        results_count=10,
        fresh_count=7,
        has_more=True,
        searched_at="2026-03-15T14:30:00+00:00",
    )
    dumped = entry.model_dump()
    restored = SearchLedgerEntry.model_validate(dumped)

    assert restored.query == entry.query
    assert restored.country == entry.country
    assert restored.remote_only == entry.remote_only
    assert restored.page == entry.page
    assert restored.results_count == entry.results_count
    assert restored.fresh_count == entry.fresh_count
    assert restored.has_more == entry.has_more
    assert restored.searched_at == entry.searched_at


def test_search_ledger_entry_rejects_missing_query() -> None:
    """Omitting query raises ValidationError."""
    with pytest.raises(ValidationError):
        SearchLedgerEntry(  # type: ignore[call-arg]
            country="gb",
            page=1,
            results_count=10,
            fresh_count=7,
            has_more=True,
            searched_at="2026-03-15T14:30:00+00:00",
        )


# ---------------------------------------------------------------------------
# log_search + get_search_ledger
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_log_search_persists_entry() -> None:
    """log_search writes 1 entry; get_search_ledger returns it with correct fields."""
    store = InMemoryStore()
    service = ProfileService(store)

    await service.log_search(
        input_data=_make_input(),
        results_count=10,
        fresh_count=7,
    )

    ledger = await service.get_search_ledger(DEFAULT_USER_ID)

    assert len(ledger) == 1
    entry = ledger[0]
    assert entry["query"] == "Python Developer in London"
    assert entry["country"] == "gb"
    assert entry["results_count"] == 10
    assert entry["fresh_count"] == 7
    assert entry["has_more"] is True  # 10 >= FETCH_NUM_PAGES * 10

    # searched_at should be a valid ISO timestamp
    datetime.fromisoformat(entry["searched_at"])


@pytest.mark.asyncio
async def test_log_search_has_more_false_when_under_page_size() -> None:
    """results_count below FETCH_NUM_PAGES*10 produces has_more=False."""
    store = InMemoryStore()
    service = ProfileService(store)

    threshold = FETCH_NUM_PAGES * 10  # currently 10
    await service.log_search(
        input_data=_make_input(),
        results_count=threshold - 4,  # 6 < 10
        fresh_count=6,
    )

    ledger = await service.get_search_ledger(DEFAULT_USER_ID)
    assert len(ledger) == 1
    assert ledger[0]["has_more"] is False


@pytest.mark.asyncio
async def test_get_search_ledger_returns_sorted_by_most_recent() -> None:
    """Three searches with staggered timestamps come back most-recent-first."""
    store = InMemoryStore()
    service = ProfileService(store)

    timestamps = [
        "2026-03-15T10:00:00+00:00",
        "2026-03-15T12:00:00+00:00",
        "2026-03-15T11:00:00+00:00",
    ]

    for ts in timestamps:
        # Write entries directly to bypass datetime.now() in log_search
        from uuid import uuid4

        entry = SearchLedgerEntry(
            query="Python Developer in London",
            country="gb",
            page=1,
            results_count=5,
            fresh_count=5,
            has_more=False,
            searched_at=ts,
        )
        await store.aput((DEFAULT_USER_ID, "search_ledger"), str(uuid4()), entry.model_dump())

    ledger = await service.get_search_ledger(DEFAULT_USER_ID)

    assert len(ledger) == 3
    # Verify descending order
    assert ledger[0]["searched_at"] == "2026-03-15T12:00:00+00:00"
    assert ledger[1]["searched_at"] == "2026-03-15T11:00:00+00:00"
    assert ledger[2]["searched_at"] == "2026-03-15T10:00:00+00:00"


@pytest.mark.asyncio
async def test_get_search_ledger_empty_store() -> None:
    """get_search_ledger returns [] when no entries have been logged."""
    store = InMemoryStore()
    service = ProfileService(store)

    ledger = await service.get_search_ledger(DEFAULT_USER_ID)
    assert ledger == []


# ---------------------------------------------------------------------------
# reset_discovery_state clears ledger
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_discovery_state_clears_ledger() -> None:
    """reset_discovery_state deletes all search_ledger entries."""
    store = InMemoryStore()
    service = ProfileService(store)

    # Log a search to populate the ledger
    await service.log_search(
        input_data=_make_input(),
        results_count=10,
        fresh_count=8,
    )
    assert len(await service.get_search_ledger(DEFAULT_USER_ID)) == 1

    # Reset wipes the ledger
    await service.reset_discovery_state(DEFAULT_USER_ID)
    assert await service.get_search_ledger(DEFAULT_USER_ID) == []
