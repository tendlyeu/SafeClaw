"""Authentication middleware for the SafeClaw API."""

import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("safeclaw.auth")


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Middleware that validates API key in the Authorization header.

    Expects: Authorization: Bearer sc_...
    Skips auth for health endpoint and when auth is disabled.
    """

    SKIP_PATHS = {"/api/v1/health", "/docs", "/openapi.json"}

    def __init__(self, app, api_key_manager=None, require_auth: bool = False):
        super().__init__(app)
        self.api_key_manager = api_key_manager
        self.require_auth = require_auth

    async def dispatch(self, request: Request, call_next):
        # Skip auth for health and docs endpoints
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        # If auth is not required (local mode), pass through
        if not self.require_auth or self.api_key_manager is None:
            return await call_next(request)

        # Extract API key from Authorization header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"error": "Missing or invalid Authorization header"},
            )

        raw_key = auth_header[7:]  # Strip "Bearer "
        api_key = self.api_key_manager.validate_key(raw_key)
        if api_key is None:
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid or revoked API key"},
            )

        # Attach org context to request state
        request.state.org_id = api_key.org_id
        request.state.api_key_scope = api_key.scope

        return await call_next(request)
