from __future__ import annotations

import asyncio
import concurrent.futures
import queue
import threading
from typing import Any, Callable, Coroutine, Optional

from app.core.logger import get_logger

logger = get_logger("core.async_bridge")


class AsyncBridge:
    """Run asyncio work on a dedicated thread and dispatch UI callbacks safely."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._queue: "queue.Queue[tuple[Callable, tuple, dict]]" = queue.Queue()
        self._state_lock = threading.Lock()
        self._closing = False
        self._shutdown_future: Optional[concurrent.futures.Future] = None
        self._thread = threading.Thread(
            target=self._run_loop, name="AsyncBridge", daemon=True
        )
        self._thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            # Defensive cleanup for unexpected loop stops. Normal shutdown
            # drains tasks and the default executor before stopping the loop.
            try:
                pending = [
                    task for task in asyncio.all_tasks(self._loop)
                    if not task.done()
                ]
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
                self._loop.run_until_complete(self._loop.shutdown_asyncgens())
                self._loop.run_until_complete(self._loop.shutdown_default_executor())
            except Exception:
                logger.exception("Error while finalizing the AsyncBridge event loop")
            finally:
                self._loop.close()
                asyncio.set_event_loop(None)

    async def _shutdown_loop(self) -> None:
        """Cancel loop tasks and wait for executor work before loop.close()."""
        current = asyncio.current_task()
        while True:
            pending = [
                task for task in asyncio.all_tasks()
                if task is not current and not task.done()
            ]
            if not pending:
                break
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)

        await self._loop.shutdown_asyncgens()
        # Cancelling asyncio.to_thread() does not stop its worker thread.
        # Executor shutdown waits for workers to finish before the loop closes.
        await self._loop.shutdown_default_executor()

    def run_coroutine(
        self,
        coro: "Coroutine[Any, Any, Any]",
        on_success: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ) -> "concurrent.futures.Future":
        """Schedule a coroutine; callbacks are dispatched to the UI thread."""
        with self._state_lock:
            if self._closing:
                coro.close()
                raise RuntimeError("AsyncBridge is shutting down.")
            future = asyncio.run_coroutine_threadsafe(coro, self._loop)

        def _on_done(fut: "concurrent.futures.Future") -> None:
            try:
                result = fut.result()
            except concurrent.futures.CancelledError:
                return
            except Exception as exc:  # noqa: BLE001 - forwarded to UI
                logger.debug("Background task failed: %s", exc)
                self.dispatch(on_error, exc)
                return
            self.dispatch(on_success, result)

        future.add_done_callback(_on_done)
        return future

    def dispatch(self, callback: Optional[Callable], *args: Any, **kwargs: Any) -> None:
        """Queue a callback for the Tk main thread's next poll()."""
        if callback is None:
            return
        self._queue.put((callback, args, kwargs))

    def poll(self) -> None:
        """Drain queued callbacks on the Tk main thread."""
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
        """Stop accepting work, drain tasks/executor, then stop and close loop.

        timeout is a diagnostic threshold, not permission to abandon running
        executor threads. Shutdown waits for their cleanup instead of closing
        an event loop while thread callbacks are still outstanding.
        """
        with self._state_lock:
            if not self._closing:
                self._closing = True
                self._shutdown_future = asyncio.run_coroutine_threadsafe(
                    self._shutdown_loop(), self._loop
                )
            shutdown_future = self._shutdown_future

        if shutdown_future is None:
            return

        try:
            shutdown_future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            logger.warning(
                "AsyncBridge cleanup exceeded %.1fs; waiting for worker cleanup",
                timeout,
            )
            shutdown_future.result()

        if self._thread.is_alive():
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join()
