import sqlite3
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.config import settings


def inspect_db() -> None:
    db_path = settings.USER_MEMORY_DB_PATH
    print(f"--- Inspecting Database: {db_path} ---")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Profile
    print("\n👤 User Profile:")
    cursor.execute("SELECT * FROM profile")
    rows = cursor.fetchall()
    if rows:
        headers = rows[0].keys()
        print(f"Columns: {list(headers)}")
        for row in rows:
            print(dict(row))
    else:
        print("(No profile found)")

    # 2. Preferences
    print("\n⚙️  Preferences:")
    cursor.execute("SELECT * FROM preferences")
    rows = cursor.fetchall()
    if rows:
        headers = rows[0].keys()
        print(f"Columns: {list(headers)}")
        for row in rows:
            print(dict(row))
    else:
        print("(No preferences found)")

    conn.close()


if __name__ == "__main__":
    inspect_db()
