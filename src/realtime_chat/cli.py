"""Command-line interface for realtime-chat: serve and admin/inspection tools."""

from __future__ import annotations

import sys

import typer
from rich.console import Console
from rich.table import Table
from sqlmodel import Session, select

from . import rooms as rooms_service
from .config import get_settings
from .db import get_engine, init_db
from .models import Room, User

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

app = typer.Typer(
    help="Run and administer the real-time chat server.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Address to bind."),
    port: int = typer.Option(8000, "--port", help="Port to listen on."),
) -> None:
    """Launch the chat server (REST API + WebSocket + SPA if built)."""
    from .web.app import run

    console.print(f"[green]Serving realtime-chat at[/green] http://{host}:{port}")
    if get_settings().is_using_default_secret:
        console.print("[yellow]Warning: using the default JWT secret. Set CHAT_JWT_SECRET for production.[/yellow]")
    console.print("[dim]Press Ctrl+C to stop.[/dim]")
    run(host=host, port=port)


@app.command()
def users() -> None:
    """List all registered users."""
    init_db()
    with Session(get_engine()) as session:
        rows = session.exec(select(User).order_by(User.id)).all()
    if not rows:
        console.print("[dim]No users yet.[/dim]")
        return
    table = Table(title="Users")
    table.add_column("ID", justify="right", style="cyan")
    table.add_column("Username")
    table.add_column("Joined")
    for u in rows:
        table.add_row(str(u.id), u.username, u.created_at.strftime("%Y-%m-%d %H:%M"))
    console.print(table)


@app.command()
def rooms() -> None:
    """List all rooms with owner, members, visibility, and expiry."""
    init_db()
    with Session(get_engine()) as session:
        rows = session.exec(select(Room).order_by(Room.created_at.desc())).all()
        if not rows:
            console.print("[dim]No rooms yet.[/dim]")
            return
        table = Table(title="Rooms")
        table.add_column("Slug", style="cyan")
        table.add_column("Name")
        table.add_column("Visibility")
        table.add_column("Members", justify="right")
        table.add_column("Expires")
        for r in rows:
            expires = "never" if r.expires_at is None else r.expires_at.strftime("%Y-%m-%d %H:%M")
            if rooms_service.is_expired(r):
                expires = f"[red]{expires} (expired)[/red]"
            table.add_row(
                r.slug, r.name,
                "private" if r.is_private else "public",
                str(rooms_service.member_count(session, r.id)),
                expires,
            )
    console.print(table)


@app.command()
def purge() -> None:
    """Delete expired rooms now (normally done automatically in the background)."""
    init_db()
    with Session(get_engine()) as session:
        removed = rooms_service.purge_expired(session)
    if removed:
        console.print(f"[green]Purged {len(removed)} expired room(s):[/green] {', '.join(removed)}")
    else:
        console.print("[dim]No expired rooms.[/dim]")


if __name__ == "__main__":
    app()
