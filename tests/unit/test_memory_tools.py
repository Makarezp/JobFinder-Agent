import unittest
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langgraph.store.memory import InMemoryStore

from app.tools.memory import delete_preference, finalize_profile, save_preference, update_my_profile


class FailingPutStore(InMemoryStore):
    def put(
        self,
        namespace: tuple[str, ...],
        key: str,
        value: dict[str, Any],
        index: list[str] | Literal[False] | None = None,
        *,
        ttl: float | None | Any = None,
    ) -> None:
        raise Exception("Database error")


class FailingDeleteStore(InMemoryStore):
    def delete(self, namespace: tuple[str, ...], key: str) -> None:
        raise Exception("Delete error")


class TestMemoryTools(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryStore()
        self.config: RunnableConfig = {"configurable": {"user_id": "test_user"}}

    def test_update_my_profile_success(self) -> None:
        # Act
        result = update_my_profile.invoke(
            {"name": "Test User", "role": "Tester", "store": self.store}, config=self.config
        )

        # Assert
        self.assertIn("Profile updated successfully", result)

        # Verify store content
        namespace = ("test_user", "profile")
        item = self.store.get(namespace, "data")
        if item is None:
            self.fail("Item not found in store")
        self.assertEqual(item.value["name"], "Test User")
        self.assertEqual(item.value["role"], "Tester")

    def test_update_my_profile_with_cv_summary(self) -> None:
        """Test that update_my_profile accepts and stores a cv_summary."""
        cv_text = "Experienced Senior Backend Dev with 5 years experience in Python."
        result = update_my_profile.invoke(
            {"name": "CV User", "cv_summary": cv_text, "store": self.store}, config=self.config
        )

        self.assertIn("Profile updated successfully", result)

        namespace = ("test_user", "profile")
        item = self.store.get(namespace, "data")
        if item is None:
            self.fail("Item not found in store")
        self.assertTrue(item.value["cv_uploaded"])
        self.assertEqual(item.value["cv_summary"], cv_text)

    def test_save_preference_success(self) -> None:
        # Act
        result = save_preference.invoke(
            {"key": "loc", "value": "rem", "category": "hard", "store": self.store}, config=self.config
        )

        # Assert
        self.assertIn("Preference saved", result)

        # Verify store content
        namespace = ("test_user", "preferences")
        item = self.store.get(namespace, "loc")
        if item is None:
            self.fail("Item not found in store")
        self.assertEqual(item.value["key"], "loc")
        self.assertEqual(item.value["value"], "rem")
        self.assertEqual(item.value["category"], "hard")

    def test_delete_preference_success(self) -> None:
        # Arrange
        namespace = ("test_user", "preferences")
        self.store.put(namespace, "loc", {"value": "rem", "category": "hard"})

        # Act
        result = delete_preference.invoke({"key": "loc", "store": self.store}, config=self.config)

        # Assert
        self.assertIn("deleted", result)

        # Verify store content
        item = self.store.get(namespace, "loc")
        self.assertIsNone(item)

    def test_delete_preference_not_found(self) -> None:
        # Arrange - don't seed anything

        # Act
        result = delete_preference.invoke({"key": "non_existent", "store": self.store}, config=self.config)

        # Assert
        self.assertIn("not found", result)

    def test_update_my_profile_error(self) -> None:
        # Arrange
        failing_store = FailingPutStore()

        # Act
        result = update_my_profile.invoke({"role": "Simulated Error", "store": failing_store}, config=self.config)
        # Assert
        self.assertIn("Error updating profile", result)
        self.assertIn("Database error", result)

    def test_save_preference_error(self) -> None:
        # Arrange
        failing_store = FailingPutStore()

        # Act
        result = save_preference.invoke({"key": "fail", "value": "val", "store": failing_store}, config=self.config)
        # Assert
        self.assertIn("Error saving preference", result)
        self.assertIn("Database error", result)

    def test_delete_preference_error(self) -> None:
        # Arrange
        failing_store = FailingDeleteStore()
        # Ensure it passes the "exists" check first
        namespace = ("test_user", "preferences")
        # Use super put to seed without raising error
        InMemoryStore.put(failing_store, namespace, "error_key", {"value": "exists", "category": "soft"})

        # Act
        result = delete_preference.invoke({"key": "error_key", "store": failing_store}, config=self.config)
        # Assert
        self.assertIn("Error deleting preference", result)
        self.assertIn("Delete error", result)

    def test_finalize_profile_success(self) -> None:
        """Test finalize_profile succeeds when profile has name/role."""
        # Arrange: seed a profile with name and role
        namespace = ("test_user", "profile")
        self.store.put(namespace, "data", {"id": 1, "name": "Alice", "role": "Dev"})

        # Act
        result = finalize_profile.invoke({"store": self.store}, config=self.config)

        # Assert
        self.assertIn("Onboarding complete", result)

    def test_finalize_profile_rejects_empty(self) -> None:
        """Test finalize_profile rejects when no name or role is set."""
        # Act — no profile seeded
        result = finalize_profile.invoke({"store": self.store}, config=self.config)

        # Assert
        self.assertIn("Cannot finalize", result)
