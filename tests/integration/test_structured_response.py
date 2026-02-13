from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.agent.constants import (
    FINAL_ANSWER_TOOL_NAME,
    JOBS_KEY,
    TEXT_RESPONSE_KEY,
)
from app.main import app

client = TestClient(app)


@pytest.mark.asyncio
async def test_chat_endpoint_structured_response() -> None:
    """
    Test the /chat endpoint when the agent returns a structured response via final_answer tool.
    """
    # Mock graph at the DI wiring point
    with patch("app.api.dependencies.graph") as mock_graph:
        # Create a mock AIMessage mimicking a tool call to final_answer
        mock_tool_call = {
            "name": FINAL_ANSWER_TOOL_NAME,
            "args": {
                TEXT_RESPONSE_KEY: "Here are some jobs.",
                JOBS_KEY: [
                    {
                        "title": "Python Dev",
                        "company": "Tech Corp",
                        "location": "London",
                        "salary": "60k",
                        "description": "Great job",
                        "apply_link": "http://example.com",
                    }
                ],
            },
            "id": "call_123",
        }

        mock_message = AIMessage(content="", tool_calls=[mock_tool_call])
        mock_graph.ainvoke = AsyncMock(return_value={"messages": [mock_message]})

        # Make the request
        response = client.post("/chat", data={"message": "find jobs"})

        assert response.status_code == 200
        # Check if the job title is rendered in the HTML
        assert "Python Dev" in response.text
        assert "Tech Corp" in response.text
        assert "Great job" in response.text
