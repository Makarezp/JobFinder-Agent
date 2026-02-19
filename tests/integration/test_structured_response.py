from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_chat_service
from app.main import app

client = TestClient(app)


@pytest.mark.asyncio
async def test_chat_endpoint_structured_response() -> None:
    """
    Test the /chat endpoint when the agent returns a structured response.
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

    # Use dependency overrides to mock the service
    app.dependency_overrides[get_chat_service] = lambda: mock_service

    try:
        # Make the request
        response = client.post("/chat", data={"message": "find jobs"})

        assert response.status_code == 200
        # Check if the job title is rendered in the HTML
        assert "Python Dev" in response.text
        assert "Tech Corp" in response.text
        assert "Great job" in response.text
    finally:
        app.dependency_overrides.clear()
