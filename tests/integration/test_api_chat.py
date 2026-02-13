from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.main import app

client = TestClient(app)


@pytest.mark.asyncio
async def test_chat_endpoint_success() -> None:
    """
    Test the /chat endpoint validates input and returns HTML.
    Mocks the agent graph to avoid real LLM calls.
    """
    mock_response = {"messages": [AIMessage(content="Hello from AI")]}

    # Patched to point to where graph is used: app.services.chat_service
    with patch("app.services.chat_service.graph.ainvoke", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = mock_response

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
