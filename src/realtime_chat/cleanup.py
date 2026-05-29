"""Background task that periodically deletes expired rooms.

Started from the app's lifespan. On each tick it purges expired rooms from the
database and closes any still-connected WebSocket clients in those rooms.
"""

from __future__ import annotations

import asyncio
import logging

from sqlmodel import Session

from . import rooms
from .config import get_settings
from .db import get_engine
from .manager import ConnectionManager

log = logging.getLogger("realtime_chat.cleanup")


async def purge_once(manager: ConnectionManager) -> list[str]:
    """Purge expired rooms once; disconnect their clients. Returns slugs purged."""
    with Session(get_engine()) as session:
        removed = rooms.purge_expired(session)
    for slug in removed:
        await manager.close_room(
            slug, {"type": "system", "content": "This room has expired and is now closed."}
        )
    if removed:
        log.info("Purged %d expired room(s): %s", len(removed), ", ".join(removed))
    return removed


async def run_cleanup_loop(manager: ConnectionManager) -> None:
    """Run purge_once forever on the configured interval (cancel-safe)."""
    interval = get_settings().cleanup_interval_seconds
    try:
        while True:
            await asyncio.sleep(interval)
            try:
                await purge_once(manager)
            except Exception:  # never let one bad tick kill the loop
                log.exception("Room cleanup tick failed")
    except asyncio.CancelledError:
        pass
