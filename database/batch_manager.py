"""Batch orchestration utilities for logs and daily stats."""
import asyncio
import atexit
import os
import signal
import threading
from typing import Optional

from database import db
from database.db import batch_logger, stats_cache

DEFAULT_FLUSH_INTERVAL = int(os.getenv("FLUSH_INTERVAL", "60"))

_flush_task: Optional[asyncio.Task] = None


def start_periodic_flush(loop: asyncio.AbstractEventLoop, interval: int = DEFAULT_FLUSH_INTERVAL) -> None:
    """Start a background task that flushes batches at a fixed interval."""

    global _flush_task
    if _flush_task and not _flush_task.done():
        return

    async def _periodic() -> None:
        while True:
            await asyncio.sleep(interval)
            await flush_all()

    _flush_task = loop.create_task(_periodic())


def register_signal_handlers(loop: asyncio.AbstractEventLoop) -> None:
    """Ensure batches are flushed before a graceful shutdown."""

    if threading.current_thread() is not threading.main_thread():
        return

    def _handler(*_: object) -> None:
        asyncio.ensure_future(flush_all(), loop=loop)

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handler)
        except NotImplementedError:  # pragma: no cover - Windows
            signal.signal(sig, lambda *_: asyncio.run(flush_all()))


async def flush_all() -> None:
    await db.flush_all()


def flush_all_sync() -> None:
    """Synchronously flush using a dedicated loop (atexit friendly)."""

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(flush_all())
    else:
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(flush_all(), loop)
            try:
                future.result(timeout=5)
            except Exception:  # noqa: BLE001 - best effort during shutdown
                pass
        else:
            loop.run_until_complete(flush_all())


atexit.register(flush_all_sync)

__all__ = [
    "batch_logger",
    "stats_cache",
    "flush_all",
    "flush_all_sync",
    "register_signal_handlers",
    "start_periodic_flush",
]
