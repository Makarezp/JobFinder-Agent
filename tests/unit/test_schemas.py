import pytest
from pydantic import ValidationError

from app.agent.schemas import JobSummary, JobSummaryBatch


class TestJobSummary:
    def test_accepts_valid_data(self) -> None:
        summary = JobSummary(job_id="abc", recommend=True, description="text")
        assert summary.job_id == "abc"
        assert summary.recommend is True
        assert summary.description == "text"

    def test_rejects_missing_job_id(self) -> None:
        with pytest.raises(ValidationError):
            JobSummary(description="text")  # type: ignore[call-arg]

    def test_rejects_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            JobSummary(job_id="x", recommend=True, description="y", pass_filter=True)  # type: ignore[call-arg]


class TestJobSummaryBatch:
    def test_round_trip(self) -> None:
        batch = JobSummaryBatch(
            summaries=[
                JobSummary(job_id="a", recommend=True, description="desc a"),
                JobSummary(job_id="b", recommend=False, description="desc b"),
            ]
        )
        dumped = batch.model_dump()
        restored = JobSummaryBatch.model_validate(dumped)
        assert len(restored.summaries) == 2
        assert restored.summaries[0].job_id == "a"
        assert restored.summaries[1].description == "desc b"
