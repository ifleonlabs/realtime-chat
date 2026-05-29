"""Command-line interface for realtime-chat: serve and inspect history."""

from __future__ import annotations

import sys

import typer
from rich.console import Console
from rich.table import Table
from sqlmodel import Session

from . import service
from .config import get_settings
from .db import get_engine, init_db

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

app = typer.Typer(
    help="Run and inspect the real-time chat server.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Address to bind."),
    port: int = typer.Option(8000, "--port", help="Port to listen on."),
) -> None:
    """Launch the chat server (web UI + WebSocket endpoint)."""
    from .web.app import run

    console.print(f"[green]Serving realtime-chat at[/green] http://{host}:{port}")
    console.print("[dim]Press Ctrl+C to stop.[/dim]")
    run(host=host, port=port)


@app.command()
def rooms() -> None:
    """List rooms that have message history, busiest first."""
    init_db()
    with Session(get_engine()) as session:
        data = service.list_rooms(session)
    if not data:
        console.print("[dim]No messages yet.[/dim]")
        return
    table = Table(title="Rooms")
    table.add_column("Room", style="cyan")
    table.add_column("Messages", justify="right", style="green")
    for room, count in data:
        table.add_row(room, str(count))
    console.print(table)


@app.command()
def history(
    room: str = typer.Argument(..., help="Room to show history for."),
    limit: int = typer.Option(20, "--limit", "-n", help="How many recent messages."),
) -> None:
    """Print recent messages for a room."""
    init_db()
    with Session(get_engine()) as session:
        messages = service.recent_messages(session, room.strip().lower(), limit)
    if not messages:
        console.print(f"[dim]No messages in {room!r}.[/dim]")
        return
    for m in messages:
        ts = m.created_at.strftime("%H:%M")
        console.print(f"[dim]{ts}[/dim] [cyan]{m.username}[/cyan]: {m.content}")


if __name__ == "__main__":
    app()
