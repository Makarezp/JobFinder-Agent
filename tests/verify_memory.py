import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.database import get_all_preferences, get_profile, init_db
from app.tools.memory import delete_preference, save_preference, update_my_profile


def test_memory_system() -> None:
    print("--- 1. Initializing DB ---")
    init_db()
    print("DB Initialized.")

    print("\n--- 2. Testing Profile Update ---")
    # update_my_profile is a structured tool, so we call it directly or via .invoke if using LangChain wrapper,
    # but here we imported the function-like tool. Let's see how @tool decorates it.
    # The @tool decorator makes it a BaseTool. We can call .invoke or .run or direct implementation if accessible.
    # For testing simpler logic, we can call the underlying function if available, or just use the tool's run method.

    # LangChain tools can be called with .invoke({"arg": val})
    res = update_my_profile.invoke({"name": "Alice Code", "role": "Senior Architect"})
    print(f"Update Result: {res}")

    profile = get_profile()
    print(f"Fetched Profile: {profile}")
    assert profile is not None
    assert profile["name"] == "Alice Code"
    assert profile["role"] == "Senior Architect"

    print("\n--- 3. Testing Preferences ---")
    res = save_preference.invoke({"key": "location", "value": "Berlin", "category": "hard"})
    print(f"Save Result: {res}")

    res = save_preference.invoke({"key": "salary", "value": 120000, "category": "hard"})
    print(f"Save Result: {res}")

    prefs = get_all_preferences()
    print(f"Fetched Preferences: {prefs}")
    assert prefs["location"] == "Berlin"
    assert prefs["salary"] == 120000

    print("\n--- 4. Testing Preference Deletion ---")
    res = delete_preference.invoke({"key": "location"})
    print(f"Delete Result: {res}")

    prefs = get_all_preferences()
    print(f"Fetched Preferences: {prefs}")
    assert "location" not in prefs

    print("\n--- ✅ Verification Successful ---")


if __name__ == "__main__":
    test_memory_system()
