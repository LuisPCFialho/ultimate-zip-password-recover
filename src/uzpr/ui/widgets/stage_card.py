from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

try:
    from qfluentwidgets import BodyLabel, CaptionLabel, CardWidget, ProgressBar
except ImportError:
    from PySide6.QtWidgets import QFrame as CardWidget  # type: ignore[assignment]
    from PySide6.QtWidgets import QLabel as BodyLabel  # type: ignore[assignment]
    from PySide6.QtWidgets import QLabel as CaptionLabel  # type: ignore[assignment]
    from PySide6.QtWidgets import QProgressBar as ProgressBar  # type: ignore[assignment]

_STATUS_COLORS = {
    "pending": "#7A7A84",
    "running": "#3B82F6",
    "found": "#22C55E",
    "exhausted": "#F97316",
    "skipped": "#7A7A84",
    "failed": "#EF4444",
}

_STATUS_ICONS = {
    "pending": "○",  # ○
    "running": "▶",  # ▶
    "found": "✔",  # ✔
    "exhausted": "□",  # □
    "skipped": "−",  # −
    "failed": "✗",  # ✗
}


def _fmt_eta(eta_s: float | None) -> str:
    if eta_s is None:
        return "ETA —"
    h = int(eta_s // 3600)
    m = int((eta_s % 3600) // 60)
    s = int(eta_s % 60)
    if h:
        return f"ETA {h}h {m:02d}m"
    if m:
        return f"ETA {m}m {s:02d}s"
    return f"ETA {s}s"


class StageCard(CardWidget):
    """Displays one attack stage's current status."""

    def __init__(
        self,
        stage_no: int,
        name: str,
        engine: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._status = "pending"

        # --- Badge: stage number ---
        self._badge = QLabel(str(stage_no))
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.setFixedSize(32, 32)
        self._badge.setStyleSheet(
            "QLabel { border-radius: 16px; background: #2B2B33;"
            " color: #B4B4BC; font-size: 12px; font-weight: bold; }"
        )

        # --- Name + engine ---
        name_layout = QVBoxLayout()
        name_layout.setSpacing(2)
        name_layout.setContentsMargins(0, 0, 0, 0)

        self._name_label = BodyLabel(name)
        self._engine_chip = QLabel(engine)
        self._engine_chip.setStyleSheet(
            "QLabel { background: #2B2B33; color: #7A7A84; border-radius: 4px;"
            " padding: 1px 6px; font-size: 11px; }"
        )

        name_layout.addWidget(self._name_label)
        name_layout.addWidget(self._engine_chip)

        # --- Right side: status icon + progress + rate/ETA ---
        right_layout = QVBoxLayout()
        right_layout.setSpacing(4)
        right_layout.setContentsMargins(0, 0, 0, 0)

        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        self._status_icon = QLabel(_STATUS_ICONS["pending"])
        self._status_icon.setStyleSheet(
            f"QLabel {{ color: {_STATUS_COLORS['pending']}; font-size: 16px; }}"
        )
        self._progress_bar = ProgressBar()
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(100)
        self._progress_bar.setValue(0)
        self._progress_bar.setMinimumWidth(120)
        self._progress_bar.setFixedHeight(6)

        status_row.addWidget(self._status_icon)
        status_row.addWidget(self._progress_bar, 1)

        self._rate_label = CaptionLabel("— c/s | ETA —")
        self._rate_label.setStyleSheet("color: #7A7A84;")

        right_layout.addLayout(status_row)
        right_layout.addWidget(self._rate_label)

        # --- Assemble main horizontal layout ---
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(10)
        main_layout.addWidget(self._badge)
        main_layout.addLayout(name_layout, 1)
        main_layout.addLayout(right_layout)

        self._apply_status_style("pending")

    # ------------------------------------------------------------------
    # Public update methods
    # ------------------------------------------------------------------

    def update_running(self, cps: float, pct: float, eta_s: float | None) -> None:
        self._apply_status_style("running")
        self._progress_bar.setValue(max(0, min(100, int(pct * 100))))
        self._rate_label.setText(f"{cps:,.0f} c/s | {_fmt_eta(eta_s)}")

    def set_found(self) -> None:
        self._apply_status_style("found")
        self._progress_bar.setValue(100)
        self._rate_label.setText("Password found!")

    def set_exhausted(self) -> None:
        self._apply_status_style("exhausted")
        self._progress_bar.setValue(100)
        self._rate_label.setText("Exhausted")

    def set_skipped(self) -> None:
        self._apply_status_style("skipped")
        self._progress_bar.setValue(0)
        self._rate_label.setText("Skipped")

    def set_pending(self) -> None:
        self._apply_status_style("pending")
        self._progress_bar.setValue(0)
        self._rate_label.setText("— c/s | ETA —")

    def set_failed(self) -> None:
        self._apply_status_style("failed")
        self._rate_label.setText("Failed")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_status_style(self, status: str) -> None:
        self._status = status
        color = _STATUS_COLORS.get(status, "#7A7A84")
        icon = _STATUS_ICONS.get(status, "○")
        self._status_icon.setText(icon)
        self._status_icon.setStyleSheet(f"QLabel {{ color: {color}; font-size: 16px; }}")
        self._badge.setStyleSheet(
            f"QLabel {{ border-radius: 16px; background: {color}22;"
            f" color: {color}; font-size: 12px; font-weight: bold; }}"
        )
