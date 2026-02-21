from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_chat_service
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_chat_dependencies() -> Any:
    """Fixture to mock chat dependencies for all tests in this module."""
    mock_service = AsyncMock()
    mock_response = {
        "user_message": "Test Message",
        "ai_message": "Hello from AI",
        "jobs": [],
    }
    mock_service.process_message.return_value = mock_response

    app.dependency_overrides[get_chat_service] = lambda: mock_service
    yield mock_service
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_chat_endpoint_success() -> None:
    """Test the /api/chat endpoint validates input and returns JSON."""
    response = client.post("/api/chat", json={"message": "Test Message"})

    assert response.status_code == 200
    data = response.json()
    assert data["user_message"] == "Test Message"
    assert data["ai_message"] == "Hello from AI"
    assert "jobs" in data


@pytest.mark.asyncio
async def test_chat_endpoint_empty_message() -> None:
    """Test validation for empty messages."""
    response = client.post("/api/chat", json={"message": ""})
    assert response.status_code in [400, 422]
    if response.status_code == 400:
        assert "Message is required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_chat_endpoint_soft_degradation(mock_chat_dependencies: AsyncMock) -> None:
    """Test that backend errors return 200 OK with a Markdown error string in ai_message."""
    mock_chat_dependencies.process_message.side_effect = RuntimeError("LLM unavailable")

    response = client.post("/api/chat", json={"message": "Test Message"})

    assert response.status_code == 200
    data = response.json()
    assert "**System Error**" in data["ai_message"]
    assert data["jobs"] == []
