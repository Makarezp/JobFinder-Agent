from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.tools.jsearch_api import jsearch_api_search


def _make_raw_job(
    job_id: str = "job_abc123",
    job_title: str = "Software Engineer",
    employer_name: str = "Acme Corp",
    job_city: str = "Chicago",
    job_state: str = "IL",
    job_country: str = "US",
    job_min_salary: float | None = 80_000,
    job_max_salary: float | None = 120_000,
    job_salary_period: str | None = "YEAR",
    job_salary: Any = None,
    job_description: str = "A" * 2000,
    job_apply_link: str | None = "https://example.com/apply",
    apply_options: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "job_title": job_title,
        "employer_name": employer_name,
        "job_city": job_city,
        "job_state": job_state,
        "job_country": job_country,
        "job_min_salary": job_min_salary,
        "job_max_salary": job_max_salary,
        "job_salary_period": job_salary_period,
        "job_salary": job_salary,
        "job_description": job_description,
        "job_apply_link": job_apply_link,
        "apply_options": apply_options or [],
    }


def _mock_response(jobs: list[dict[str, Any]]) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": jobs}
    mock_resp.raise_for_status.return_value = None
    return mock_resp


@pytest.fixture(autouse=True)
def patch_api_key() -> Any:
    with patch("app.tools.jsearch_api.settings") as mock_settings:
        mock_settings.JSEARCH_API_KEY = "test-key"
        yield mock_settings


class TestJSearchFieldMapping:
    def test_maps_basic_fields_correctly(self) -> None:
        raw = _make_raw_job()
        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.return_value = _mock_response([raw])
            result = jsearch_api_search.invoke({"query": "software engineer"})

        assert isinstance(result, list)
        assert len(result) == 1
        job = result[0]
        assert job["id"] == "job_abc123"
        assert job["title"] == "Software Engineer"
        assert job["company"] == "Acme Corp"
        assert job["apply_link"] == "https://example.com/apply"

    def test_location_concatenated_correctly(self) -> None:
        raw = _make_raw_job(job_city="London", job_state="", job_country="GB")
        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.return_value = _mock_response([raw])
            result = jsearch_api_search.invoke({"query": "python developer"})

        assert isinstance(result, list)
        job = result[0]
        # Empty state should be excluded
        assert job["location"] == "London, GB"

    def test_location_all_parts_present(self) -> None:
        raw = _make_raw_job(job_city="Chicago", job_state="IL", job_country="US")
        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.return_value = _mock_response([raw])
            result = jsearch_api_search.invoke({"query": "engineer"})

        assert isinstance(result, list)
        assert result[0]["location"] == "Chicago, IL, US"


class TestSalaryFormatting:
    def test_salary_formatted_with_min_max_and_period(self) -> None:
        raw = _make_raw_job(job_min_salary=80_000, job_max_salary=120_000, job_salary_period="YEAR")
        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.return_value = _mock_response([raw])
            result = jsearch_api_search.invoke({"query": "engineer"})

        assert isinstance(result, list)
        assert result[0]["salary"] == "$80,000 - $120,000 per YEAR"

    def test_salary_min_only(self) -> None:
        raw = _make_raw_job(job_min_salary=50_000, job_max_salary=None, job_salary_period="YEAR")
        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.return_value = _mock_response([raw])
            result = jsearch_api_search.invoke({"query": "engineer"})

        assert isinstance(result, list)
        assert result[0]["salary"] == "From $50,000 per YEAR"

    def test_salary_fallback_to_job_salary_field(self) -> None:
        raw = _make_raw_job(job_min_salary=None, job_max_salary=None, job_salary=70_000)
        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.return_value = _mock_response([raw])
            result = jsearch_api_search.invoke({"query": "engineer"})

        assert isinstance(result, list)
        assert result[0]["salary"] == "70000"

    def test_salary_none_when_all_fields_missing(self) -> None:
        raw = _make_raw_job(job_min_salary=None, job_max_salary=None, job_salary=None)
        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.return_value = _mock_response([raw])
            result = jsearch_api_search.invoke({"query": "engineer"})

        assert isinstance(result, list)
        assert result[0]["salary"] is None


class TestDescriptionTruncation:
    def test_full_description_truncated_at_1000_chars(self) -> None:
        raw = _make_raw_job(job_description="X" * 5000)
        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.return_value = _mock_response([raw])
            result = jsearch_api_search.invoke({"query": "engineer"})

        assert isinstance(result, list)
        assert len(result[0]["full_description"]) == 1000

    def test_full_description_not_padded_when_short(self) -> None:
        short_desc = "Short description."
        raw = _make_raw_job(job_description=short_desc)
        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.return_value = _mock_response([raw])
            result = jsearch_api_search.invoke({"query": "engineer"})

        assert isinstance(result, list)
        assert result[0]["full_description"] == short_desc

    def test_description_snippet_truncated_at_300_chars(self) -> None:
        raw = _make_raw_job(job_description="Y" * 1000)
        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.return_value = _mock_response([raw])
            result = jsearch_api_search.invoke({"query": "engineer"})

        assert isinstance(result, list)
        assert len(result[0]["description"]) == 300


class TestApplyLinkFallback:
    def test_apply_link_falls_back_to_apply_options(self) -> None:
        raw = _make_raw_job(
            job_apply_link=None,
            apply_options=[{"apply_link": "https://fallback.com/apply"}],
        )
        # Override the key since _make_raw_job sets a default
        raw["job_apply_link"] = None
        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.return_value = _mock_response([raw])
            result = jsearch_api_search.invoke({"query": "engineer"})

        assert isinstance(result, list)
        assert result[0]["apply_link"] == "https://fallback.com/apply"


class TestErrorHandling:
    def test_returns_error_string_when_api_key_missing(self) -> None:
        with patch("app.tools.jsearch_api.settings") as mock_settings:
            mock_settings.JSEARCH_API_KEY = None
            result = jsearch_api_search.invoke({"query": "engineer"})

        assert isinstance(result, str)
        assert "JSEARCH_API_KEY" in result

    def test_returns_error_string_on_http_status_error(self) -> None:
        import httpx

        with patch("httpx.Client") as mock_client_cls:
            mock_resp = MagicMock()
            mock_resp.status_code = 429
            mock_resp.text = "Too Many Requests"
            mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError("429", request=MagicMock(), response=mock_resp)
            mock_client_cls.return_value.__enter__.return_value.get.return_value = mock_resp

            result = jsearch_api_search.invoke({"query": "engineer"})

        assert isinstance(result, str)
        assert "429" in result

    def test_returns_error_string_on_request_error(self) -> None:
        import httpx

        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.side_effect = httpx.RequestError("Connection refused")
            result = jsearch_api_search.invoke({"query": "engineer"})

        assert isinstance(result, str)
        assert "Error" in result

    def test_returns_empty_list_when_data_is_empty(self) -> None:
        with patch("httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__.return_value.get.return_value = _mock_response([])
            result = jsearch_api_search.invoke({"query": "engineer"})

        assert result == []


class TestRequestParams:
    def test_num_pages_is_always_forced_to_1(self) -> None:
        raw = _make_raw_job()
        with patch("httpx.Client") as mock_client_cls:
            mock_get = mock_client_cls.return_value.__enter__.return_value.get
            mock_get.return_value = _mock_response([raw])

            jsearch_api_search.invoke({"query": "engineer", "page": 3})

            call_kwargs = mock_get.call_args
            params = call_kwargs.kwargs.get("params") or call_kwargs.args[1] if call_kwargs.args else call_kwargs.kwargs["params"]
            assert params["num_pages"] == "1"
            assert params["page"] == "3"

    def test_remote_only_maps_to_work_from_home(self) -> None:
        raw = _make_raw_job()
        with patch("httpx.Client") as mock_client_cls:
            mock_get = mock_client_cls.return_value.__enter__.return_value.get
            mock_get.return_value = _mock_response([raw])

            jsearch_api_search.invoke({"query": "engineer", "remote_only": True})

            call_kwargs = mock_get.call_args
            params = call_kwargs.kwargs["params"]
            assert params.get("work_from_home") == "true"
