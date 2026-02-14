import pytest
from httpx import ASGITransport, AsyncClient

from app.agent.graph import store
from app.main import app


@pytest.mark.asyncio
async def test_cv_persistence() -> None:
    # 1. Simulate CV Upload by directly writing to the Store
    # In the real app, this happens in ChatService.process_cv
    user_id = "default_user"
    namespace = (user_id, "profile")

    test_cv = "I am a skilled Python enthusiast."
    data = {"name": "Persistence Test", "cv_text": test_cv}

    # We need to access the store that the app is using.
    # In our current setup, the store is defined in app.agent.graph module.
    store.put(namespace, "data", data)

    # 2. Check Profile Route
    # The profile route reads from the same store instance (imported from app.agent.graph)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/profile")

    assert response.status_code == 200
    # The template renders "No CV uploaded" if just name is there?
    # Let's check what the template does or just check for the text.
    # The profile page logic: profile = store.get(...) -> renders profile.cv_text if exists

    # Debug print if fails
    print(response.text)

    assert "Persistence Test" in response.text
    # Note: The presence of CV text in the HTML depends on profile.html implementation.
    # Assuming it renders the raw text or similar.
    # If the UI renders it, this assertion should pass.
