"""Convenience entry point so you can run the app directly.

Examples:
    python main.py serve
    python main.py rooms
    python main.py history general

It hands control to the Typer app defined in src/realtime_chat/cli.py.
"""

from __future__ import annotations

import os
import sys

# Make `src/` importable when running this file directly, without installing.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from realtime_chat.cli import app  # noqa: E402

if __name__ == "__main__":
    app()
