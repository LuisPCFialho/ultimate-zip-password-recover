from __future__ import annotations

"""Home page — dashboard with recent jobs and New Job CTA."""

import time
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

try:
    from qfluentwidgets import (
        BodyLabel,
        CaptionLabel,
        CardWidget,
        PrimaryPushButton,
        ScrollArea,
        SubtitleLabel,
        TitleLabel,
    )
except ImportError:
    from PySide6.QtWidgets import QFrame as CardWidget  # type: ignore[assignment]
    from PySide6.QtWidgets import QLabel as BodyLabel  # type: ignore[assignment]
    from PySide6.QtWidgets import QLabel as CaptionLabel  # type: ignore[assignment]
    from PySide6.QtWidgets import QLabel as SubtitleLabel  # type: ignore[assignment]
    from PySide6.QtWidgets import QLabel as TitleLabel  # type: ignore[assignment]
    from PySide6.QtWidgets import QPushButton as PrimaryPushButton  # type: ignore[assignment]
    from PySide6.QtWidgets import QScrollArea as ScrollArea  # type: ignore[assignment]

from uzpr.ui.widgets.drop_zone import DropZone

if TYPE_CHECKING:
    from uzpr.app import AppState
    from uzpr.persistence.models import SessionRow

_FORMAT_LABELS: dict[str, str] = {
    "zip-classic": "ZIP",
    "zip-aes": "ZIP-AES",
    "rar3-hp": "RAR3",
    "rar5": "RAR5",
    "pkware-strong": "PKWARE",
    "plain": "PLAIN",
    "unsupported": "???",
}

_STATUS_COLORS: dict[str, str] = {
    "pending": "#7A7A84",
    "running": "#3B82F6",
    "paused": "#F59E0B",
    "found": "#22C55E",
    "exhausted": "#F97316",
    "cancelled": "#EF4444",
    "failed": "#EF4444",
}


def _elapsed_label(started: float, ended: float | None = None) -> str:
    delta = (ended or time.time()) - started
    h = int(delta // 3600)
    m = int((delta % 3600) // 60)
    s = int(delta % 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


class _StatCard(CardWidget):
    def __init__(self, title: str, value: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        title_lbl = CaptionLabel(title)
        title_lbl.setStyleSheet("color: #7A7A84;")

        self._value_lbl = TitleLabel(value)

        layout.addWidget(title_lbl)
        layout.addWidget(self._value_lbl)

    def set_value(self, value: str) -> None:
        self._value_lbl.setText(value)


class _RecentJobRow(QFrame):
    clicked: Signal = Signal(str)  # session_id

    def __init__(self, session: SessionRow, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session_id = session.id
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "QFrame { border-radius: 8px; background: transparent; }"
            "QFrame:hover { background: rgba(255,255,255,0.04); }"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        archive_name = Path(session.archive_path).name
        name_lbl = BodyLabel(archive_name)
        name_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        fmt_str = _FORMAT_LABELS.get(session.archive_format, session.archive_format.upper())
        fmt_chip = QWidget()
        fmt_chip_layout = QHBoxLayout(fmt_chip)
        fmt_chip_layout.setContentsMargins(6, 2, 6, 2)
        fmt_label = CaptionLabel(fmt_str)
        fmt_label.setStyleSheet(
            "color: #B4B4BC; background: #2B2B33; border-radius: 4px; padding: 1px 5px;"
        )
        fmt_chip_layout.addWidget(fmt_label)

        color = _STATUS_COLORS.get(session.status, "#7A7A84")
        status_lbl = CaptionLabel(session.status.upper())
        status_lbl.setStyleSheet(
            f"color: {color}; background: {color}22; border-radius: 4px; padding: 1px 6px;"
        )

        elapsed = _elapsed_label(session.created_at, session.updated_at)
        time_lbl = CaptionLabel(elapsed)
        time_lbl.setStyleSheet("color: #7A7A84;")

        layout.addWidget(name_lbl, 1)
        layout.addWidget(fmt_label)
        layout.addWidget(status_lbl)
        layout.addWidget(time_lbl)

    def mousePressEvent(self, event: object) -> None:
        self.clicked.emit(self._session_id)


class HomePage(ScrollArea):
    file_selected: Signal = Signal(Path)
    session_clicked: Signal = Signal(str)  # session_id

    def __init__(self, app_state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app = app_state
        self.setObjectName("homePage")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._container = QWidget()
        self._outer_layout = QHBoxLayout(self._container)
        self._outer_layout.setContentsMargins(24, 24, 24, 24)
        self._outer_layout.setSpacing(20)

        # ---- Left column ----
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(16)

        # Quick-start card
        self._quick_card = CardWidget()
        quick_inner = QVBoxLayout(self._quick_card)
        quick_inner.setContentsMargins(20, 20, 20, 20)
        quick_inner.setSpacing(14)

        quick_title = SubtitleLabel("Quick Start")
        quick_inner.addWidget(quick_title)

        self._drop_zone = DropZone()
        self._drop_zone.file_dropped.connect(self.file_selected)
        quick_inner.addWidget(self._drop_zone)

        self._new_job_btn = PrimaryPushButton("New Recovery Job")
        self._new_job_btn.setFixedHeight(38)
        self._new_job_btn.clicked.connect(self._on_new_job_clicked)
        quick_inner.addWidget(self._new_job_btn)

        left_layout.addWidget(self._quick_card)

        # Recent jobs card
        self._recent_card = CardWidget()
        recent_inner = QVBoxLayout(self._recent_card)
        recent_inner.setContentsMargins(20, 16, 20, 16)
        recent_inner.setSpacing(8)

        recent_title = SubtitleLabel("Recent Jobs")
        recent_inner.addWidget(recent_title)

        self._recent_list_layout = QVBoxLayout()
        self._recent_list_layout.setSpacing(4)
        self._no_jobs_lbl = BodyLabel("No recent jobs")
        self._no_jobs_lbl.setStyleSheet("color: #7A7A84;")
        self._no_jobs_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._recent_list_layout.addWidget(self._no_jobs_lbl)
        recent_inner.addLayout(self._recent_list_layout)

        left_layout.addWidget(self._recent_card)
        left_layout.addStretch(1)

        # ---- Right column: stats ----
        right = QWidget()
        right.setFixedWidth(220)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        stats_title = SubtitleLabel("Stats")
        right_layout.addWidget(stats_title)

        self._stat_sessions = _StatCard("Total Sessions", "—")
        self._stat_found = _StatCard("Passwords Found", "—")
        self._stat_hours = _StatCard("Hours Spent", "—")

        right_layout.addWidget(self._stat_sessions)
        right_layout.addWidget(self._stat_found)
        right_layout.addWidget(self._stat_hours)
        right_layout.addStretch(1)

        self._outer_layout.addWidget(left, 1)
        self._outer_layout.addWidget(right)

        self.setWidget(self._container)

    # ------------------------------------------------------------------
    # Qt lifecycle
    # ------------------------------------------------------------------

    def showEvent(self, event: object) -> None:
        super().showEvent(event)  # type: ignore[arg-type]
        self._load_recent_sessions()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _on_new_job_clicked(self) -> None:
        """Open file dialog as a shortcut to starting a new job without drag-drop."""
        from PySide6.QtWidgets import QFileDialog

        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Select Archive",
            "",
            "Archive files (*.zip *.rar);;All files (*)",
        )
        if path_str:
            self.file_selected.emit(Path(path_str))

    def _load_recent_sessions(self) -> None:
        try:
            import asyncio

            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self._async_load_sessions())
            else:
                self._load_sessions_sync()
        except Exception:
            self._load_sessions_sync()

    def _load_sessions_sync(self) -> None:
        try:
            repo = self._app.repo
            sessions = repo._sync_list_sessions(None)
            sessions.sort(key=lambda s: s.updated_at, reverse=True)
            self._populate_recent(sessions[:5])
            self._update_stats(sessions)
        except Exception:
            pass

    async def _async_load_sessions(self) -> None:
        try:
            sessions = await self._app.repo.list_sessions()
            sessions.sort(key=lambda s: s.updated_at, reverse=True)
            self._populate_recent(sessions[:5])
            self._update_stats(sessions)
        except Exception:
            pass

    def _populate_recent(self, sessions: list[SessionRow]) -> None:
        # Clear existing
        while self._recent_list_layout.count():
            item = self._recent_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not sessions:
            self._no_jobs_lbl = BodyLabel("No recent jobs")
            self._no_jobs_lbl.setStyleSheet("color: #7A7A84;")
            self._no_jobs_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._recent_list_layout.addWidget(self._no_jobs_lbl)
            return

        for session in sessions:
            row = _RecentJobRow(session)
            row.clicked.connect(self.session_clicked)
            self._recent_list_layout.addWidget(row)

    def _update_stats(self, sessions: list[SessionRow]) -> None:
        total = len(sessions)
        found = sum(1 for s in sessions if s.status == "found")
        total_s = sum(s.updated_at - s.created_at for s in sessions)
        hours = total_s / 3600.0

        self._stat_sessions.set_value(str(total))
        self._stat_found.set_value(str(found))
        self._stat_hours.set_value(f"{hours:.1f}")
