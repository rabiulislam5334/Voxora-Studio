from __future__ import annotations

import asyncio
import concurrent.futures
import queue
import threading
from typing import Any, Callable, Coroutine, Optional

from app.core.logger import get_logger

logger = get_logger("core.async_bridge")


class AsyncBridge:
    """Run asyncio work on a dedicated thread and dispatch results to Tk.

    Shutdown cancels and drains loop tasks before closing the loop. Blocking
    functions already running in asyncio's default executor cannot be forcibly
    stopped; their worker threads are allowed to finish independently.
    """

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._queue: "queue.Queue[tuple[Callable, tuple, dict]]" = queue.Queue()
        self._state_lock = threading.Lock()
        self._closing = False
        self._thread = threading.Thread(
            target=self._run_loop, name="AsyncBridge", daemon=True
        )
        self._thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            # Tasks must be cancelled and awaited while the loop is still
            # running; otherwise Python reports "Task was destroyed but it
            # is pending" when the loop is closed.
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            if pending:
                self._loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            self._loop.close()

    def run_coroutine(
        self,
        coro: "Coroutine[Any, Any, Any]",
        on_success: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> "asyncio.Future":
        """Schedule work. Completion callbacks are queued for Tk's main thread."""
        with self._state_lock:
            if self._closing:
                coro.close()
                raise RuntimeError("AsyncBridge is shutting down")
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)

        def _on_done(fut: "asyncio.Future") -> None:
            try:
                result = fut.result()
            except (asyncio.CancelledError, concurrent.futures.CancelledError):
                return
            except Exception as exc:  # noqa: BLE001 - forwarded to UI
                logger.debug("Background task failed: %s", exc)
                self.dispatch(on_error, exc)
                return
            self.dispatch(on_success, result)

        future.add_done_callback(_on_done)
        return future

    def dispatch(self, callback: Optional[Callable], *args: Any, **kwargs: Any) -> None:
        """Thread-safe: queue a callback to run on the Tk main thread next poll()."""
        if callback is None:
            return
        self._queue.put((callback, args, kwargs))

    def poll(self) -> None:
        """Call periodically from the Tk main thread (via root.after)."""
        while True:
            try:
                callback, args, kwargs = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback(*args, **kwargs)
            except Exception:
                logger.exception("Unhandled error in dispatched UI callback")

    def shutdown(self, timeout: float = 2.0) -> None:
        """Stop accepting work, cancel loop tasks, and wait for loop cleanup."""
        with self._state_lock:
            if not self._closing:
                self._closing = True
                self._loop.call_soon_threadsafe(self._loop.stop)

        if threading.current_thread() is self._thread:
            logger.warning("AsyncBridge.shutdown() called from its own loop thread")
            return

        self._thread.join(timeout=max(0.0, timeout))
        if self._thread.is_alive():
            logger.warning(
                "AsyncBridge thread did not shut down within %.1fs", timeout
            )
