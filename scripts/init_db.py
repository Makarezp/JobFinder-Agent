import asyncio
import logging
import sys
from pathlib import Path

# Add project root to sys.path to allow running as a standalone script
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from app.core.database import init_db  # noqa: E402

# Configure printing for the script output
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


async def main() -> None:
    """Initialize the database tables."""
    try:
        await init_db()
    except Exception as e:
        print(f"Error initializing database: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
