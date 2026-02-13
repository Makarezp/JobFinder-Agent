import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from app.main import app
from langchain_core.messages import AIMessage

client = TestClient(app)


@pytest.mark.asyncio
async def test_chat_endpoint_structured_response():
    """
    Test the /chat endpoint when the agent returns a structured response via final_answer tool.
    """
    # Mock graph execution
    with patch("app.api.routes.graph.ainvoke", new_callable=AsyncMock) as mock_ainvoke:
        # Create a mock AIMessage mimicking a tool call to final_answer
        mock_tool_call = {
            "name": "final_answer",
            "args": {
                "text_response": "Here are some jobs.",
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
            },
            "id": "call_123",
        }

        mock_message = AIMessage(content="", tool_calls=[mock_tool_call])
        mock_ainvoke.return_value = {"messages": [mock_message]}

        # Make the request
        response = client.post("/chat", data={"message": "find jobs"})

        assert response.status_code == 200
        # Check if the job title is rendered in the HTML
        assert "Python Dev" in response.text
        assert "Tech Corp" in response.text
        assert "Great job" in response.text
