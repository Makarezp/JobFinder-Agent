import json
import sqlite3
from typing import Any

from app.core import queries
from app.core.config import settings


def get_db_connection() -> sqlite3.Connection:
    """Establish a connection to the SQLite database."""
    if not settings.DATA_DIR.exists():
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(settings.USER_MEMORY_DB_PATH))
    conn.row_factory = sqlite3.Row  # Access columns by name
    return conn


def init_db() -> None:
    """Initialize the database tables if they do not exist."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Profile Table (Singleton - enforced by id=1 check)
        cursor.execute(queries.CREATE_PROFILE_TABLE)

        # Preferences Table (Key-Value store with flexible JSON value)
        cursor.execute(queries.CREATE_PREFERENCES_TABLE)

        conn.commit()
    finally:
        conn.close()


# --- CRUD: Profile ---


def get_profile() -> dict[str, Any] | None:
    """Retrieve the user profile."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(queries.SELECT_PROFILE)
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        conn.close()


def update_profile(name: str | None = None, role: str | None = None, cv_text: str | None = None) -> dict[str, Any]:
    """
    Update the user profile. Creates it if it doesn't exist.
    Only updates fields that are provided (not None).
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Check if profile exists
        cursor.execute("SELECT * FROM profile WHERE id = 1")
        exists = cursor.fetchone()

        if exists:
            # Dynamic Update
            fields = []
            values = []
            if name is not None:
                fields.append("name = ?")
                values.append(name)
            if role is not None:
                fields.append("role = ?")
                values.append(role)
            if cv_text is not None:
                fields.append("cv_text = ?")
                values.append(cv_text)

            if fields:
                query = (
                    f"{queries.UPDATE_PROFILE_BASE} {', '.join(fields)}, updated_at = CURRENT_TIMESTAMP WHERE id = 1"
                )
                cursor.execute(query, values)
        else:
            # Insert new
            cursor.execute(queries.INSERT_PROFILE, (name, role, cv_text))

        conn.commit()

        # Return the updated profile
        return get_profile() or {}
    finally:
        conn.close()


# --- CRUD: Preferences ---


def get_all_preferences() -> dict[str, Any]:
    """Retrieve all preferences as a simple dictionary."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(queries.SELECT_ALL_PREFERENCES)
        rows = cursor.fetchall()

        result = {}
        for row in rows:
            try:
                # SQLite stores JSON as text, so we parse it back
                val = json.loads(row["value"])
            except (json.JSONDecodeError, TypeError):
                val = row["value"]

            # Return full object with metadata
            result[row["key"]] = {"value": val, "category": row["category"] or "soft"}
        return result
    finally:
        conn.close()


def save_preference(key: str, value: Any, category: str = "soft") -> None:
    """Save a preference. Value is JSON serialized."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        json_value = json.dumps(value)

        cursor.execute(
            queries.UPSERT_PREFERENCE,
            (key, json_value, category),
        )
        conn.commit()
    finally:
        conn.close()


def delete_preference(key: str) -> bool:
    """Delete a preference by key. Returns True if deleted."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(queries.DELETE_PREFERENCE, (key,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()
