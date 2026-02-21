from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_chat_service
from app.main import app

client = TestClient(app)


@pytest.mark.asyncio
async def test_chat_endpoint_structured_response() -> None:
    """
    Test the /api/chat endpoint when the agent returns a structured response with jobs.
    """
    mock_service = AsyncMock()
    mock_response = {
        "user_message": "find jobs",
        "ai_message": "Here are some jobs.",
        "jobs": [
            {
                "title": "Python Dev",
                "company": "Tech Corp",
                "location": "London",
                "salary": "60k",
                "description": "Great job",
                "apply_link": "http://example.com",
            }
        ],
    }
    mock_service.process_message.return_value = mock_response

    app.dependency_overrides[get_chat_service] = lambda: mock_service

    try:
        response = client.post("/api/chat", json={"message": "find jobs"})

        assert response.status_code == 200
        data = response.json()
        assert data["user_message"] == "find jobs"
        assert data["ai_message"] == "Here are some jobs."
        assert len(data["jobs"]) == 1
        job = data["jobs"][0]
        assert job["title"] == "Python Dev"
        assert job["company"] == "Tech Corp"
        assert job["description"] == "Great job"
    finally:
        app.dependency_overrides.clear()
