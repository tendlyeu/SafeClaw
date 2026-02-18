"""SafeClaw FastAPI application - the neurosymbolic governance service."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from safeclaw.api.middleware import TimingMiddleware
from safeclaw.auth.middleware import APIKeyAuthMiddleware
from safeclaw.config import SafeClawConfig
from safeclaw.engine.full_engine import FullEngine

logger = logging.getLogger("safeclaw")

# Module-level config singleton — read once, reused by lifespan and middleware (R3-30)
_config = SafeClawConfig()

engine: FullEngine | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine
    logging.basicConfig(level=getattr(logging, _config.log_level, logging.INFO))
    logger.info("Starting SafeClaw engine...")
    engine = FullEngine(_config)
    logger.info("SafeClaw engine ready")
    yield
    logger.info("Shutting down SafeClaw engine")
    # Known benign race: engine may still be referenced by in-flight requests
    # during shutdown. This is acceptable because the process is exiting and
    # uvicorn drains connections before calling the lifespan teardown. (R3-50)
    engine = None


app = FastAPI(
    title="SafeClaw",
    description="Neurosymbolic governance layer for autonomous AI agents",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS - configurable via SAFECLAW_CORS_ORIGIN_REGEX env var (R3-31)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=_config.cors_origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth middleware — uses the same _config instance (R3-30, R3-32)
if _config.require_auth:
    logger.warning(
        "require_auth=True but no api_key_manager is configured. "
        "Auth will be a no-op until a key manager is provided."
    )
app.add_middleware(APIKeyAuthMiddleware, require_auth=_config.require_auth)

# Request timing
app.add_middleware(TimingMiddleware)


def get_engine() -> FullEngine:
    if engine is None:
        raise RuntimeError("Engine not initialized — call startup first")
    return engine


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "version": "0.1.0", "engine_ready": engine is not None}


# Import and include API routes
from safeclaw.api.routes import router  # noqa: E402

app.include_router(router, prefix="/api/v1")
