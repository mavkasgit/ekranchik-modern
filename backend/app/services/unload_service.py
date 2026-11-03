"""
This service is a placeholder.
The original file was missing, causing a server error.
"""

import logging

logger = logging.getLogger(__name__)


class UnloadService:
    def get_unload_events(self, limit: int = 100) -> list[dict]:
        logger.warning("UnloadService is not implemented. Returning empty list.")
        return []


unload_service = UnloadService()
