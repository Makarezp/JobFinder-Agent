import pytest
from langgraph.store.memory import InMemoryStore

from app.services.profile_service import ProfileService

TEST_USER = "testuser41"

JOB_A = {
    "id": "abc123def456",
    "title": "Python Developer",
    "company": "Acme Corp",
    "location": "London",
    "salary": "£60,000",
    "description": "Build backend services.",
    "apply_link": "https://example.com/job-1",
}

JOB_B = {
    "id": "def456abc789",
    "title": "ML Engineer",
    "company": "StartupX",
    "location": "Remote",
    "salary": None,
    "description": "Train models.",
    "apply_link": "https://example.com/job-2",
}


@pytest.fixture
def service() -> ProfileService:
    return ProfileService(store=InMemoryStore())


@pytest.mark.asyncio
async def test_add_then_get_returns_added_jobs(service: ProfileService) -> None:
    """add_pending_jobs followed by get_pending_jobs returns the added jobs."""
    await service.add_pending_jobs([JOB_A, JOB_B], TEST_USER)
    jobs = await service.get_pending_jobs(TEST_USER)

    ids = {j.id for j in jobs}
    assert JOB_A["id"] in ids
    assert JOB_B["id"] in ids
    assert len(jobs) == 2


@pytest.mark.asyncio
async def test_add_preserves_job_fields(service: ProfileService) -> None:
    """Added job fields are correctly stored and retrieved."""
    await service.add_pending_jobs([JOB_A], TEST_USER)
    jobs = await service.get_pending_jobs(TEST_USER)

    job = jobs[0]
    assert job.title == JOB_A["title"]
    assert job.company == JOB_A["company"]
    assert job.location == JOB_A["location"]
    assert job.salary == JOB_A["salary"]
    assert job.description == JOB_A["description"]
    assert job.apply_link == JOB_A["apply_link"]
    assert job.added_at  # must be populated


@pytest.mark.asyncio
async def test_remove_then_get_excludes_removed_job(service: ProfileService) -> None:
    """remove_pending_job followed by get_pending_jobs no longer includes the removed job."""
    await service.add_pending_jobs([JOB_A, JOB_B], TEST_USER)
    await service.remove_pending_job(JOB_A["id"], TEST_USER)
    jobs = await service.get_pending_jobs(TEST_USER)

    ids = {j.id for j in jobs}
    assert JOB_A["id"] not in ids
    assert JOB_B["id"] in ids
    assert len(jobs) == 1


@pytest.mark.asyncio
async def test_add_duplicate_does_not_create_duplicate(service: ProfileService) -> None:
    """Adding the same job twice (same id) results in only one entry."""
    await service.add_pending_jobs([JOB_A], TEST_USER)
    await service.add_pending_jobs([JOB_A], TEST_USER)
    jobs = await service.get_pending_jobs(TEST_USER)

    assert len(jobs) == 1


@pytest.mark.asyncio
async def test_empty_store_returns_empty_list(service: ProfileService) -> None:
    """get_pending_jobs on a fresh store returns an empty list."""
    jobs = await service.get_pending_jobs(TEST_USER)
    assert jobs == []


def test_pending_job_without_full_description_defaults_to_none() -> None:
    """PendingJob deserialises correctly when full_description is absent."""
    from app.agent.memory_schema import PendingJob

    job = PendingJob(**{**JOB_A, "added_at": "2026-01-01T00:00:00+00:00"})
    assert job.full_description is None


def test_pending_job_with_full_description_serialises_field() -> None:
    """PendingJob with full_description serialises it into the dict."""
    from app.agent.memory_schema import PendingJob

    job = PendingJob(**{**JOB_A, "added_at": "2026-01-01T00:00:00+00:00", "full_description": "Full job text here."})
    data = job.model_dump()
    assert data["full_description"] == "Full job text here."
