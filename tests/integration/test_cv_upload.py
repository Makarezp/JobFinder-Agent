from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_chat_service
from app.main import app

client = TestClient(app)


@pytest.mark.asyncio
async def test_upload_cv_endpoint() -> None:
    """
    Test the /upload-cv endpoint.
    Mocks PdfReader and chat service.
    Verifies CV text is parsed and processed.
    """
    pdf_content = b"%PDF-1.4 dummy content"
    file = {"file": ("resume.pdf", pdf_content, "application/pdf")}

    mock_service = AsyncMock()
    mock_service.process_cv.return_value = {"user_message": "CV Uploaded", "ai_message": "I received your CV."}

    # Use dependency overrides to mock the service
    app.dependency_overrides[get_chat_service] = lambda: mock_service

    try:
        from unittest.mock import patch

        with patch("app.services.chat_service.PdfReader") as mock_pdf_reader:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "Parsed CV Info: Python Developer"

            mock_instance = mock_pdf_reader.return_value
            mock_instance.pages = [mock_page]

            response = client.post("/upload-cv", files=file)

            assert response.status_code == 200
            assert "I received your CV" in response.text

            # Verify process_cv was called with the correct bytes
            assert mock_service.process_cv.called
            args, kwargs = mock_service.process_cv.call_args
            assert args[0] == pdf_content
            assert kwargs["filename"] == "resume.pdf"
    finally:
        app.dependency_overrides.clear()
