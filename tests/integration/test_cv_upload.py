from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.agent.constants import CV_RAW_TEXT_KEY
from app.main import app

client = TestClient(app)


@pytest.mark.asyncio
async def test_upload_cv_endpoint() -> None:
    """
    Test the /upload-cv endpoint.
    Mocks PdfReader and graph execution.
    Verifies CV text is injected as cv_raw_text (not persisted to store).
    """
    pdf_content = b"%PDF-1.4 dummy content"
    file = {"file": ("resume.pdf", pdf_content, "application/pdf")}

    with patch("app.services.chat_service.PdfReader") as mock_pdf_reader:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Parsed CV Info: Python Developer"

        mock_instance = mock_pdf_reader.return_value
        mock_instance.pages = [mock_page]

        with patch("app.api.dependencies.graph") as mock_graph:
            mock_graph.ainvoke = AsyncMock(return_value={"messages": [MagicMock(content="I received your CV.")]})

            response = client.post("/upload-cv", files=file)

            assert response.status_code == 200
            assert "I received your CV" in response.text

            # Verify ainvoke was called with cv_raw_text in inputs
            assert mock_graph.ainvoke.called
            call_args = mock_graph.ainvoke.call_args[0][0]
            assert CV_RAW_TEXT_KEY in call_args
            assert call_args[CV_RAW_TEXT_KEY] == "Parsed CV Info: Python Developer"
