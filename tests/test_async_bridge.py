from __future__ import annotations

import asyncio
import threading
import time

import pytest

from app.core.async_bridge import AsyncBridge


def test_shutdown_cancels_and_drains_pending_coroutine():
    bridge = AsyncBridge()
    started = threading.Event()
    cancelled = threading.Event()

    async def wait_forever():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    future = bridge.run_coroutine(wait_forever())
    assert started.wait(2.0)

    bridge.shutdown(timeout=2.0)

    assert future.done()
    assert future.cancelled()
    assert cancelled.is_set()
    assert not bridge._thread.is_alive()


def test_shutdown_cancels_to_thread_task_without_destroyed_pending_task():
    bridge = AsyncBridge()
    worker_started = threading.Event()
    worker_finished = threading.Event()

    def blocking_work():
        worker_started.set()
        time.sleep(0.15)
        worker_finished.set()

    async def run_blocking_work():
        await asyncio.to_thread(blocking_work)

    future = bridge.run_coroutine(run_blocking_work())
    assert worker_started.wait(2.0)

    # The asyncio task is cancelled promptly. The already-running executor
    # function is not cancellable, but is finite and may finish afterwards.
    bridge.shutdown(timeout=2.0)

    assert future.done()
    assert future.cancelled()
    assert not bridge._thread.is_alive()
    assert worker_finished.wait(1.0)


def test_shutdown_rejects_new_coroutines_and_closes_them():
    bridge = AsyncBridge()
    bridge.shutdown(timeout=2.0)

    async def late_work():
        return None

    coro = late_work()
    with pytest.raises(RuntimeError, match="shutting down"):
        bridge.run_coroutine(coro)

    assert coro.cr_frame is None
