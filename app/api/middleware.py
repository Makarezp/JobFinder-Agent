"""FastAPI middleware for request correlation and timing."""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import request_id_var

logger = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assigns a short request_id to every HTTP request and logs timing."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:  # type: ignore[type-arg]
        # Use incoming header or generate a new one
        rid = request.headers.get("X-Request-ID", uuid.uuid4().hex[:8])
        request_id_var.set(rid)

        logger.info(
            "%s %s started",
            request.method,
            request.url.path,
        )

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000)

        response.headers["X-Request-ID"] = rid
        logger.info(
            "%s %s completed",
            request.method,
            request.url.path,
            extra={"status_code": response.status_code, "duration_ms": duration_ms},
        )
        return response
