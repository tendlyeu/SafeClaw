"""CLI serve command - starts the SafeClaw service."""

import os
from pathlib import Path

import typer


def _default_host() -> str:
    """Auto-detect Docker environment and default to 0.0.0.0 inside containers."""
    if Path("/.dockerenv").exists() or os.environ.get("CONTAINER", ""):
        return "0.0.0.0"
    return "127.0.0.1"


def serve_cmd(
    host: str = typer.Option(
        None,
        help="Host to bind to (default: 0.0.0.0 in containers, 127.0.0.1 otherwise)",
    ),
    port: int = typer.Option(8420, help="Port to listen on"),
    reload: bool = typer.Option(False, help="Enable auto-reload for development"),
):
    """Start the SafeClaw governance service."""
    import uvicorn

    if host is None:
        host = _default_host()

    if host == "0.0.0.0":
        typer.echo(
            "Warning: Binding to 0.0.0.0 (all interfaces). "
            "Use --host 127.0.0.1 to restrict to localhost only."
        )

    typer.echo(f"Starting SafeClaw on {host}:{port}")
    uvicorn.run(
        "safeclaw.main:app",
        host=host,
        port=port,
        reload=reload,
    )
