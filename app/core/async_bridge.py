from __future__ import annotations

import asyncio
import queue
import threading
from typing import Any, Callable, Coroutine, Optional

from app.core.logger import get_logger

logger = get_logger("core.async_bridge")


class AsyncBridge:
    """Runs an asyncio event loop on a dedicated background thread and
    provides a thread-safe way to get results back onto the Tk main thread.

    Tkinter widgets must only be touched from the main thread. Any
    background work (TTS calls, voice discovery, audio playback) reports
    back through `dispatch()`; the main window drains the queue on a
    `root.after()` timer by calling `poll()`.
    """

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._queue: "queue.Queue[tuple[Callable, tuple, dict]]" = queue.Queue()
        self._thread = threading.Thread(
            target=self._run_loop, name="AsyncBridge", daemon=True
        )
        self._thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run_coroutine(
        self,
        coro: "Coroutine[Any, Any, Any]",
        on_success: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> "asyncio.Future":
        """Schedule a coroutine on the background loop. `on_success`/`on_error`
        are invoked on the Tk main thread (via dispatch + poll), never here."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)

        def _on_done(fut: "asyncio.Future") -> None:
            try:
                result = fut.result()
            except Exception as exc:  # noqa: BLE001 - forwarded to UI, not swallowed
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
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            logger.warning(
                "AsyncBridge thread did not shut down within %.1fs", timeout
            )