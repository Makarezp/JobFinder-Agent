import sqlite3
import sys
from pathlib import Path

from tabulate import tabulate  # type: ignore

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core.database import DB_PATH


def inspect_db() -> None:
    print(f"--- Inspecting Database: {DB_PATH} ---")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Profile
    print("\n👤 User Profile:")
    cursor.execute("SELECT * FROM profile")
    rows = cursor.fetchall()
    if rows:
        headers = rows[0].keys()
        data = [dict(row).values() for row in rows]
        print(tabulate(data, headers=headers, tablefmt="grid"))
    else:
        print("(No profile found)")

    # 2. Preferences
    print("\n⚙️  Preferences:")
    cursor.execute("SELECT * FROM preferences")
    rows = cursor.fetchall()
    if rows:
        headers = rows[0].keys()
        data = [dict(row).values() for row in rows]
        print(tabulate(data, headers=headers, tablefmt="grid"))
    else:
        print("(No preferences found)")

    conn.close()


if __name__ == "__main__":
    inspect_db()
