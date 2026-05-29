"""Background task that periodically deletes expired messages.

Started from the app's lifespan. Clients also hide messages locally the moment
they pass their expiry, so the chat looks like messages roll off one by one;
this task is what actually reclaims the rows in the database.
"""

from __future__ import annotations

import asyncio
import logging

from sqlmodel import Session

from . import messages
from .config import get_settings
from .db import get_engine

log = logging.getLogger("realtime_chat.cleanup")


def purge_once() -> int:
    """Delete expired messages once. Returns how many were removed."""
    with Session(get_engine()) as session:
        removed = messages.purge_expired(session)
    if removed:
        log.info("Purged %d expired message(s)", removed)
    return removed


async def run_cleanup_loop() -> None:
    """Run purge_once forever on the configured interval (cancel-safe)."""
    interval = get_settings().cleanup_interval_seconds
    try:
        while True:
            await asyncio.sleep(interval)
            try:
                purge_once()
            except Exception:  # never let one bad tick kill the loop
                log.exception("Message cleanup tick failed")
    except asyncio.CancelledError:
        pass
