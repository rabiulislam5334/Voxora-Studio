from __future__ import annotations

import asyncio
import threading

import pytest

from app.core.async_bridge import AsyncBridge


def test_shutdown_cancels_pending_coroutines_and_closes_loop():
    bridge = AsyncBridge()
    started = threading.Event()

    async def wait_forever():
        started.set()
        await asyncio.Event().wait()

    future = bridge.run_coroutine(wait_forever())
    assert started.wait(timeout=2.0)

    bridge.shutdown()

    assert future.done()
    assert bridge._loop.is_closed()
    assert not bridge._thread.is_alive()


def test_shutdown_waits_for_to_thread_worker_before_closing_loop():
    bridge = AsyncBridge()
    started = threading.Event()
    release = threading.Event()

    def blocking_work():
        started.set()
        assert release.wait(timeout=3.0)

    async def run_worker():
        await asyncio.to_thread(blocking_work)

    future = bridge.run_coroutine(run_worker())
    assert started.wait(timeout=2.0)
    release.set()
    future.result(timeout=3.0)

    bridge.shutdown()

    assert bridge._loop.is_closed()
    assert not bridge._thread.is_alive()


def test_bridge_rejects_new_work_after_shutdown():
    bridge = AsyncBridge()
    bridge.shutdown()

    coro = asyncio.sleep(0)
    with pytest.raises(RuntimeError, match="shutting down"):
        bridge.run_coroutine(coro)

    assert coro.cr_frame is None
    assert bridge._loop.is_closed()
