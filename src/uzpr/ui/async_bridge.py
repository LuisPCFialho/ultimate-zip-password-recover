from __future__ import annotations

"""qasync bridge: connects anyio/asyncio event loop to Qt signals at 10 Hz."""

import asyncio
from collections import deque
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal

from uzpr.core.stages.protocol import StageEvent


class EventCoalescer(QObject):
    """Batches StageEvents at 10 Hz and emits them as a list to the UI."""

    events_ready: Signal = Signal(list)  # emits list[StageEvent]

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._queue: deque[StageEvent] = deque()
        self._timer = QTimer(self)
        self._timer.setInterval(100)  # 10 Hz
        self._timer.timeout.connect(self._flush)
        self._timer.start()

    def push(self, event: StageEvent) -> None:
        """Enqueue an event; must be called from the Qt thread."""
        self._queue.append(event)

    def _flush(self) -> None:
        if self._queue:
            batch = list(self._queue)
            self._queue.clear()
            self.events_ready.emit(batch)


def make_event_sink(coalescer: EventCoalescer) -> Callable[[StageEvent], asyncio.coroutines]:
    """Return an async EventSink that routes StageEvents to the Qt coalescer.

    The sink is safe to call from an asyncio coroutine running on the qasync
    event loop (which runs on the Qt main thread), so `call_soon_threadsafe`
    is not needed — a direct `push` is sufficient.
    """

    async def on_event(event: StageEvent) -> None:
        loop = asyncio.get_event_loop()
        loop.call_soon_threadsafe(coalescer.push, event)

    return on_event
