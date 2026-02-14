import pytest
from httpx import ASGITransport, AsyncClient

from app.agent.graph import store
from app.main import app


@pytest.mark.asyncio
async def test_cv_persistence() -> None:
    """Test that profile with cv_summary is persisted and visible on /profile."""
    user_id = "default_user"
    namespace = (user_id, "profile")

    # Simulate a profile with structured cv_summary (as stored by the onboarding agent)
    data = {
        "name": "Persistence Test",
        "role": "Senior Python Developer",
        "cv_summary": {
            "professional_summary": "Experienced Python developer with 5 years of backend work.",
            "seniority_level": "Senior",
            "years_of_experience": 5,
            "primary_domain": "Backend",
            "skills": {
                "primary": ["Python", "FastAPI"],
                "secondary": ["React"],
                "tools": ["Docker", "AWS"],
            },
            "experience": [
                {
                    "company": "Acme Corp",
                    "title": "Senior Developer",
                    "duration": "3 years",
                    "highlights": "Led backend team",
                }
            ],
            "education": ["BSc Computer Science"],
        },
        "cv_uploaded": True,
    }

    store.put(namespace, "data", data)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/profile")

    assert response.status_code == 200
    assert "Persistence Test" in response.text
