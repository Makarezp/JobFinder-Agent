# Profile Queries
CREATE_PROFILE_TABLE = """
CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT,
    role TEXT,
    cv_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

SELECT_PROFILE = "SELECT name, role, cv_text FROM profile WHERE id = 1"

INSERT_PROFILE = "INSERT INTO profile (id, name, role, cv_text) VALUES (1, ?, ?, ?)"

# Updates are dynamic, so we keep the base string here
UPDATE_PROFILE_BASE = "UPDATE profile SET "

# Preferences Queries
CREATE_PREFERENCES_TABLE = """
CREATE TABLE IF NOT EXISTS preferences (
    key TEXT PRIMARY KEY,
    value JSON,
    category TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

SELECT_ALL_PREFERENCES = "SELECT key, value FROM preferences"

UPSERT_PREFERENCE = """
INSERT INTO preferences (key, value, category, updated_at)
VALUES (?, ?, ?, CURRENT_TIMESTAMP)
ON CONFLICT(key) DO UPDATE SET
    value = excluded.value,
    category = excluded.category,
    updated_at = CURRENT_TIMESTAMP
"""

DELETE_PREFERENCE = "DELETE FROM preferences WHERE key = ?"
