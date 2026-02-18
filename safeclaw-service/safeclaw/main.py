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

engine: FullEngine | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine
    config = SafeClawConfig()
    logging.basicConfig(level=getattr(logging, config.log_level, logging.INFO))
    logger.info("Starting SafeClaw engine...")
    engine = FullEngine(config)
    logger.info("SafeClaw engine ready")
    yield
    logger.info("Shutting down SafeClaw engine")
    engine = None


app = FastAPI(
    title="SafeClaw",
    description="Neurosymbolic governance layer for autonomous AI agents",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS - allow the TS plugin to connect from any origin (localhost or remote)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth middleware
app.add_middleware(APIKeyAuthMiddleware, require_auth=getattr(SafeClawConfig(), 'require_auth', False))

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
