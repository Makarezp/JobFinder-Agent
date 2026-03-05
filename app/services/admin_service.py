import structlog

from app.core.database import reset_db_state

logger = structlog.get_logger(__name__)


class AdminService:
    """
    Service for administrative tasks and system management.
    """

    async def reset_system(self) -> None:
        """
        Performs a full system reset, including wiping the database.
        """
        logger.warning("AdminService: Initiating full system reset.")
        await reset_db_state()
