import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from app.main import app

client = TestClient(app)


@pytest.mark.asyncio
async def test_upload_cv_endpoint():
    """
    Test the /upload-cv endpoint.
    Mocks PdfReader and graph execution.
    """
    # Create a dummy PDF file
    pdf_content = b"%PDF-1.4 dummy content"
    file = {"file": ("resume.pdf", pdf_content, "application/pdf")}

    # Mock PdfReader to return text
    with patch("app.api.routes.PdfReader") as mock_pdf_reader:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Parsed CV Info: Python Developer"

        mock_instance = mock_pdf_reader.return_value
        mock_instance.pages = [mock_page]

        # Mock graph methods
        with (
            patch("app.api.routes.graph.update_state") as mock_update_state,
            patch(
                "app.api.routes.graph.ainvoke", new_callable=AsyncMock
            ) as mock_ainvoke,
        ):
            mock_ainvoke.return_value = {
                "messages": [MagicMock(content="I received your CV.")]
            }

            response = client.post("/upload-cv", files=file)

            assert response.status_code == 200
            assert "I received your CV" in response.text

            # Verify update_state was called with correct text
            assert mock_update_state.called
            args, _ = mock_update_state.call_args
            assert args[1]["cv_text"] == "Parsed CV Info: Python Developer\n"
