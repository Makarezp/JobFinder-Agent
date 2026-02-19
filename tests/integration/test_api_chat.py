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
    }
    mock_service.process_message.return_value = mock_response

    # Use dependency overrides to mock the service
    app.dependency_overrides[get_chat_service] = lambda: mock_service
    yield mock_service
    # Clean up overrides
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_chat_endpoint_success() -> None:
    """
    Test the /chat endpoint validates input and returns HTML.
    Mocks the chat service to avoid real LLM/DB calls.
    """
    response = client.post("/chat", data={"message": "Test Message"})

    assert response.status_code == 200
    content = response.text
    assert "Test Message" in content
    assert "Hello from AI" in content
    assert "bg-blue-600" in content
    assert "bg-indigo-100" in content


@pytest.mark.asyncio
async def test_chat_endpoint_empty_message() -> None:
    """Test validation for empty messages."""
    response = client.post("/chat", data={"message": ""})
    assert response.status_code in [400, 422]
    if response.status_code == 400:
        assert "Message is required" in response.json()["detail"]
