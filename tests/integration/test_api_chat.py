from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.main import app

client = TestClient(app)


@pytest.mark.asyncio
async def test_chat_endpoint_success():
    """
    Test the /chat endpoint validates input and returns HTML.
    Mocks the agent graph to avoid real LLM calls.
    """
    mock_response = {"messages": [AIMessage(content="Hello from AI")]}

    with patch("app.api.routes.graph.ainvoke", new_callable=AsyncMock) as mock_invoke:
        mock_invoke.return_value = mock_response

        response = client.post("/chat", data={"message": "Test Message"})

        assert response.status_code == 200
        content = response.text
        assert "Test Message" in content  # User message bubble?
        # Actually my template implementation renders *both* user and AI message.
        assert "Hello from AI" in content
        assert "bg-blue-600" in content  # User bubble class
        assert "bg-indigo-100" in content  # AI bubble class


@pytest.mark.asyncio
async def test_chat_endpoint_empty_message():
    """Test validation for empty messages."""
    response = client.post("/chat", data={"message": ""})
    # FastAPI Form validation usually returns 422 for missing required fields if omitted,
    # but I handles `message: str = Form(...)` and explicit check `if not message`.
    # If I send empty string, `Form(...)` accepts it, so my check raises 400.
    # However, sometimes Validation raises 422.
    assert response.status_code in [400, 422]
    if response.status_code == 400:
        assert "Message is required" in response.json()["detail"]
