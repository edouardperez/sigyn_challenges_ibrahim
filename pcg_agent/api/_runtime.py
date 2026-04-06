"""Singleton runtime holder for the compiled graph and shared resources.

This avoids circular imports: main.py initializes the runtime,
and routes.py reads it via get_runtime().
"""

from __future__ import annotations

from typing import Optional

_runtime: Optional[dict] = None


def set_runtime(runtime: dict) -> None:
    global _runtime
    _runtime = runtime


def get_runtime() -> Optional[dict]:
    return _runtime
