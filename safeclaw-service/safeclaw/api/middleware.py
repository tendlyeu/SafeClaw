"""API middleware - CORS, error handling, timing."""

import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("safeclaw.api")


class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        response = await call_next(request)
        elapsed_ms = (time.monotonic() - start) * 1000
        response.headers["X-SafeClaw-Time-Ms"] = f"{elapsed_ms:.1f}"
        if elapsed_ms > 200:
            logger.warning(f"{request.url.path} took {elapsed_ms:.1f}ms (target: <200ms)")
        return response
