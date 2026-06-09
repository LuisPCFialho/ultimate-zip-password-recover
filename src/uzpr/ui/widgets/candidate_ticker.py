from __future__ import annotations

"""Live candidate ticker — shows the last N password candidates being tested."""

from collections import deque

from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel

_FIXED_HEIGHT_PER_ROW = 18
_MIN_OPACITY = 20
_MAX_OPACITY = 100


class CandidateTicker(QWidget):
    """Shows the last N password candidates being tested (live reassurance widget)."""

    def __init__(self, n: int = 5, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._n = n
        self._history: deque[str] = deque(maxlen=n)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._labels: list[CaptionLabel] = []
        for _ in range(n):
            lbl = CaptionLabel("", self)
            lbl.setFixedHeight(_FIXED_HEIGHT_PER_ROW)
            layout.addWidget(lbl)
            self._labels.append(lbl)

        self.setFixedHeight(n * _FIXED_HEIGHT_PER_ROW)
        self._refresh()

    def push(self, candidate: str) -> None:
        """Add a candidate and refresh the display."""
        self._history.appendleft(candidate)
        self._refresh()

    def _refresh(self) -> None:
        items = list(self._history)
        # Pad to n slots
        items += [""] * (self._n - len(items))

        for i, (label, text) in enumerate(zip(self._labels, items, strict=False)):
            label.setText(text)
            opacity = _opacity_for_index(i, self._n)
            label.setStyleSheet(f"color: rgba(220, 220, 220, {opacity}%);")

    def clear(self) -> None:
        self._history.clear()
        self._refresh()


def _opacity_for_index(index: int, total: int) -> int:
    """Newest (index 0) → 100 %, oldest (index total-1) → ~20 %."""
    if total <= 1:
        return _MAX_OPACITY
    frac = index / (total - 1)
    return round(_MAX_OPACITY - frac * (_MAX_OPACITY - _MIN_OPACITY))
