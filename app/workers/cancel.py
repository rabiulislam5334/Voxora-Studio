from __future__ import annotations

import threading

from app.core.exceptions import GenerationCancelled


class CancelToken:
    """Thread-safe cancellation flag shared between the UI thread (which
    calls cancel()) and background work (which polls `cancelled` or calls
    raise_if_cancelled() at safe points)."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self, message: str = "Generation cancelled.") -> None:
        if self._event.is_set():
            raise GenerationCancelled(message)