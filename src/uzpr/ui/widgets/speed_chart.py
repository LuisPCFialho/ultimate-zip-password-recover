from __future__ import annotations

"""Rolling 60-second candidates/sec sparkline drawn with QPainter."""

from collections import deque

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

_BG_COLOR = QColor(30, 30, 30)
_GRID_COLOR = QColor(60, 60, 60)
_LINE_COLOR = QColor(0, 120, 212)  # Windows accent blue #0078D4
_LABEL_COLOR = QColor(220, 220, 220)
_FIXED_HEIGHT = 80


class SpeedChart(QWidget):
    """Rolling 60-second candidates/sec sparkline drawn with QPainter."""

    def __init__(
        self,
        parent: QWidget | None = None,
        max_points: int = 600,
    ) -> None:
        super().__init__(parent)
        self._samples: deque[float] = deque(maxlen=max_points)
        self.setFixedHeight(_FIXED_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def push(self, cps: float) -> None:
        """Add a new cps sample and trigger repaint."""
        self._samples.append(cps)
        self.update()

    def clear(self) -> None:
        self._samples.clear()
        self.update()

    def paintEvent(self, event: object) -> None:
        if not self.isVisible():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Background
        painter.fillRect(0, 0, w, h, _BG_COLOR)

        samples = list(self._samples)
        if not samples:
            painter.end()
            return

        max_val = max(samples) or 1.0
        current = samples[-1]

        # Grid lines at 25 / 50 / 75 %
        pen = QPen(_GRID_COLOR)
        pen.setWidth(1)
        painter.setPen(pen)
        for frac in (0.25, 0.50, 0.75):
            y = int(h * frac)
            painter.drawLine(0, y, w, y)

        # Sparkline path
        n = len(samples)
        path = QPainterPath()
        for i, val in enumerate(samples):
            x = int(i * (w - 1) / max(n - 1, 1))
            y = int(h - 1 - (val / max_val) * (h - 2))
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        pen = QPen(_LINE_COLOR)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawPath(path)

        # Labels: max top-right, current bottom-right
        painter.setPen(QPen(_LABEL_COLOR))
        font = painter.font()
        font.setPointSize(7)
        painter.setFont(font)

        max_text = f"max {_fmt_cps(max_val)}"
        cur_text = f"{_fmt_cps(current)}"

        margin = 4
        painter.drawText(
            QRect(0, margin, w - margin, 16),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
            max_text,
        )
        painter.drawText(
            QRect(0, h - 16 - margin, w - margin, 16),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
            cur_text,
        )

        painter.end()


def _fmt_cps(cps: float) -> str:
    if cps >= 1_000_000_000:
        return f"{cps / 1_000_000_000:.1f} Gcps"
    if cps >= 1_000_000:
        return f"{cps / 1_000_000:.1f} Mcps"
    if cps >= 1_000:
        return f"{cps / 1_000:.1f} kcps"
    return f"{cps:.0f} cps"
