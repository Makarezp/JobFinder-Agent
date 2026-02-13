import unittest
from unittest.mock import MagicMock, patch

from app.tools.memory import delete_preference, save_preference, update_my_profile


class TestMemoryTools(unittest.TestCase):
    @patch("app.tools.memory.db_update_profile")
    def test_update_my_profile_success(self, mock_db: MagicMock) -> None:
        # Arrange
        mock_db.return_value = {"name": "Test User", "role": "Tester"}

        # Act
        result = update_my_profile.invoke({"name": "Test User", "role": "Tester"})

        # Assert
        mock_db.assert_called_once_with(name="Test User", role="Tester")
        self.assertIn("Profile updated successfully", result)

    @patch("app.tools.memory.db_update_profile")
    def test_update_my_profile_error(self, mock_db: MagicMock) -> None:
        # Arrange
        mock_db.side_effect = Exception("DB Error")

        # Act
        result = update_my_profile.invoke({"name": "Test User"})

        # Assert
        self.assertIn("Error updating profile", result)

    @patch("app.tools.memory.db_save_preference")
    def test_save_preference_success(self, mock_db: MagicMock) -> None:
        # Arrange
        mock_db.return_value = None

        # Act
        result = save_preference.invoke({"key": "loc", "value": "rem", "category": "hard"})

        # Assert
        mock_db.assert_called_once_with("loc", "rem", "hard")
        self.assertIn("Preference saved", result)

    @patch("app.tools.memory.db_save_preference")
    def test_save_preference_error(self, mock_db: MagicMock) -> None:
        # Arrange
        mock_db.side_effect = Exception("DB Error")

        # Act
        result = save_preference.invoke({"key": "loc", "value": "rem"})

        # Assert
        self.assertIn("Error saving preference", result)

    @patch("app.tools.memory.db_delete_preference")
    def test_delete_preference_success(self, mock_db: MagicMock) -> None:
        # Arrange
        mock_db.return_value = True

        # Act
        result = delete_preference.invoke({"key": "loc"})

        # Assert
        mock_db.assert_called_once_with("loc")
        self.assertIn("deleted", result)

    @patch("app.tools.memory.db_delete_preference")
    def test_delete_preference_not_found(self, mock_db: MagicMock) -> None:
        # Arrange
        mock_db.return_value = False

        # Act
        result = delete_preference.invoke({"key": "loc"})

        # Assert
        self.assertIn("not found", result)

    @patch("app.tools.memory.db_delete_preference")
    def test_delete_preference_error(self, mock_db: MagicMock) -> None:
        # Arrange
        mock_db.side_effect = Exception("DB Error")

        # Act
        result = delete_preference.invoke({"key": "loc"})

        # Assert
        self.assertIn("Error deleting preference", result)
