"""SafeClaw FastAPI application - the neurosymbolic governance service."""

import logging
import time
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from safeclaw.api.errors import SafeClawError
from safeclaw.api.middleware import TimingMiddleware
from safeclaw.auth.middleware import APIKeyAuthMiddleware
from safeclaw.config import SafeClawConfig
from safeclaw.engine.full_engine import FullEngine

logger = logging.getLogger("safeclaw")

# Module-level config singleton — read once, reused by lifespan and middleware (R3-30)
_config = SafeClawConfig()

engine: FullEngine | None = None
_start_time = time.monotonic()


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

# Auth middleware — uses SQLite key manager when db_path is configured
_api_key_manager = None
if _config.require_auth and _config.db_path:
    from safeclaw.auth.api_key import SQLiteAPIKeyManager
    _api_key_manager = SQLiteAPIKeyManager(_config.db_path)
app.add_middleware(
    APIKeyAuthMiddleware,
    api_key_manager=_api_key_manager,
    require_auth=_config.require_auth,
)

# Request timing
app.add_middleware(TimingMiddleware)


@app.exception_handler(SafeClawError)
async def safeclaw_error_handler(request: Request, exc: SafeClawError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "detail": exc.detail, "hint": exc.hint},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.error("Unhandled error: %s\n%s", exc, traceback.format_exc())
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_ERROR",
            "detail": "An unexpected error occurred.",
            "hint": "Check service logs for details.",
        },
    )


def get_engine() -> FullEngine:
    if engine is None:
        raise SafeClawError(
            code="ENGINE_NOT_READY",
            detail="Engine not initialized — the service is still starting up.",
            hint="Wait a moment and retry, or check service logs.",
            status_code=503,
        )
    return engine


@app.get("/api/v1/health")
async def health():
    result = {
        "status": "ok",
        "version": "0.1.0",
        "engine_ready": engine is not None,
        "uptime_seconds": round(time.monotonic() - _start_time),
    }
    if engine is not None:
        result["components"] = {
            "knowledge_graph": {"triples": len(engine.kg)},
            "llm": {"configured": engine.llm_client is not None},
            "sessions": {"active": len(engine.session_tracker._sessions)},
            "agents": {
                "registered": len(engine.agent_registry.list_agents()),
                "active": sum(
                    1 for a in engine.agent_registry.list_agents() if not a.killed
                ),
            },
        }
    return result


# Import and include API routes
from safeclaw.api.routes import router  # noqa: E402

app.include_router(router, prefix="/api/v1")

# Admin dashboard (FastHTML sub-app)
from safeclaw.dashboard.app import create_dashboard  # noqa: E402

app.mount("/admin", create_dashboard(get_engine, mount_prefix="/admin"))
