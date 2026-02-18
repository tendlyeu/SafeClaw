"""CLI serve command - starts the SafeClaw service."""

import typer


def serve_cmd(
    host: str = typer.Option("127.0.0.1", help="Host to bind to"),
    port: int = typer.Option(8420, help="Port to listen on"),
    reload: bool = typer.Option(False, help="Enable auto-reload for development"),
):
    """Start the SafeClaw governance service."""
    import uvicorn

    typer.echo(f"Starting SafeClaw on {host}:{port}")
    uvicorn.run(
        "safeclaw.main:app",
        host=host,
        port=port,
        reload=reload,
    )
