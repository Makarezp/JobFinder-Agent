import structlog

from app.agent.constants import DEFAULT_USER_ID
from app.core.database import reset_db_state, reset_workspace_state
from app.services.profile_service import ProfileService

logger = structlog.get_logger(__name__)


class AdminService:
    """
    Service for administrative tasks and system management.
    """

    def __init__(self, profile_service: ProfileService) -> None:
        self._profile_service = profile_service

    async def reset_system(self) -> None:
        """
        Performs a full system reset, including wiping the database.
        """
        logger.warning("AdminService: Initiating full system reset.")
        await reset_db_state()

    async def reset_discovery(self, user_id: str = DEFAULT_USER_ID) -> None:
        """
        Resets only the discovery graph state: checkpoints and job-related store namespaces.
        The profile graph and profile/preferences store namespaces are left untouched.
        """
        logger.warning("AdminService: Initiating discovery reset.", user_id=user_id)
        await reset_workspace_state("discovery")
        await self._profile_service.reset_discovery_state(user_id)
        logger.info("AdminService: Discovery reset complete.", user_id=user_id)
