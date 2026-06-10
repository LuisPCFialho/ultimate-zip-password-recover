from __future__ import annotations

"""Active Jobs page — live session dashboard with sparkline and stage cards."""

import time
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

try:
    from qfluentwidgets import (
        BodyLabel,
        CaptionLabel,
        CardWidget,
        InfoBar,
        InfoBarPosition,
        PrimaryPushButton,
        ProgressBar,
        PushButton,
        StrongBodyLabel,
        TitleLabel,
    )
except ImportError:
    from PySide6.QtWidgets import QFrame as CardWidget  # type: ignore[assignment]
    from PySide6.QtWidgets import QLabel as BodyLabel  # type: ignore[assignment]
    from PySide6.QtWidgets import QLabel as CaptionLabel  # type: ignore[assignment]

    InfoBar = None  # type: ignore[assignment,misc]
    InfoBarPosition = None  # type: ignore[assignment,misc]
    from PySide6.QtWidgets import QLabel as StrongBodyLabel  # type: ignore[assignment]
    from PySide6.QtWidgets import QLabel as TitleLabel  # type: ignore[assignment]
    from PySide6.QtWidgets import QProgressBar as ProgressBar  # type: ignore[assignment]
    from PySide6.QtWidgets import QPushButton as PrimaryPushButton  # type: ignore[assignment]
    from PySide6.QtWidgets import QPushButton as PushButton  # type: ignore[assignment]

from uzpr.ui.widgets.stage_card import StageCard

if TYPE_CHECKING:
    from uzpr.app import AppState
    from uzpr.core.stages.protocol import StageEvent
    from uzpr.ui.async_bridge import EventCoalescer

_STATUS_COLORS: dict[str, str] = {
    "pending": "#7A7A84",
    "running": "#3B82F6",
    "paused": "#F59E0B",
    "found": "#22C55E",
    "exhausted": "#F97316",
    "cancelled": "#EF4444",
    "failed": "#EF4444",
}

_SPARKLINE_HISTORY = 600  # 60 s at 10 Hz


class _SparklineWidget(QWidget):
    """Draws last N samples as a filled sparkline using QPainter."""

    def __init__(self, capacity: int = _SPARKLINE_HISTORY, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: deque[float] = deque([0.0] * capacity, maxlen=capacity)
        self.setMinimumHeight(80)
        self.setMinimumWidth(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(100)

    def push(self, value: float) -> None:
        self._data.append(value)
        self.update()

    def paintEvent(self, event: object) -> None:
        w = self.width()
        h = self.height()
        data = list(self._data)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        painter.fillRect(0, 0, w, h, QColor("#0F0F12"))

        max_val = max(data) if any(v > 0 for v in data) else 1.0
        n = len(data)
        if n < 2:
            painter.end()
            return

        def _x(i: int) -> float:
            return i * w / (n - 1)

        def _y(v: float) -> float:
            return h - (v / max_val) * (h - 8) - 4

        pen = QPen(QColor("#3B82F6"), 1)
        painter.setPen(pen)

        for i in range(1, n):
            x0 = _x(i - 1)
            y0 = _y(data[i - 1])
            x1 = _x(i)
            y1 = _y(data[i])
            painter.drawLine(int(x0), int(y0), int(x1), int(y1))

        # Axis label
        painter.setPen(QPen(QColor("#7A7A84"), 1))
        painter.drawText(4, h - 4, "60 s")
        if max_val > 0:
            label = f"{max_val:,.0f} c/s"
            painter.drawText(4, 14, label)

        painter.end()


class _CandidateTicker(QWidget):
    """Shows last N candidates being tested, scrolling upward."""

    def __init__(self, capacity: int = 5, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._capacity = capacity
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)
        self._labels: list[QLabel] = []
        for _ in range(capacity):
            lbl = QLabel("")
            lbl.setStyleSheet(
                "font-family: 'Consolas', monospace; color: #7A7A84; font-size: 12px;"
            )
            layout.addWidget(lbl)
            self._labels.append(lbl)

    def push(self, candidate: str) -> None:
        texts = [lbl.text() for lbl in self._labels[1:]] + [candidate]
        for lbl, text in zip(self._labels, texts, strict=False):
            lbl.setText(text)
            lbl.setStyleSheet(
                "font-family: 'Consolas', monospace;"
                f" color: {'#E8E8EE' if text == candidate else '#7A7A84'};"
                " font-size: 12px;"
            )


class ActiveJobsPage(QWidget):
    """Live session dashboard."""

    def __init__(self, app_state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app = app_state
        self.setObjectName("activeJobsPage")

        self._session_id: str | None = None
        self._session_status: str = "pending"
        self._start_time: float = time.time()
        self._found_password: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # --- Header ---
        header_row = QHBoxLayout()
        self._archive_label = TitleLabel("No active session")
        self._status_chip = QLabel("—")
        self._status_chip.setStyleSheet(
            "QLabel { border-radius: 4px; padding: 2px 10px; "
            "background: #2B2B33; color: #7A7A84; font-size: 12px; }"
        )
        self._elapsed_label = CaptionLabel("0s")
        self._elapsed_label.setStyleSheet("color: #7A7A84;")
        header_row.addWidget(self._archive_label, 1)
        header_row.addWidget(self._status_chip)
        header_row.addWidget(self._elapsed_label)
        root.addLayout(header_row)

        # --- Overall progress ---
        progress_card = CardWidget()
        progress_inner = QVBoxLayout(progress_card)
        progress_inner.setContentsMargins(16, 12, 16, 12)
        progress_inner.setSpacing(6)
        progress_inner.addWidget(StrongBodyLabel("Overall Progress"))
        self._overall_progress = ProgressBar()
        self._overall_progress.setMinimum(0)
        self._overall_progress.setMaximum(100)
        self._overall_progress.setValue(0)
        progress_inner.addWidget(self._overall_progress)
        root.addWidget(progress_card)

        # --- Main split: stages left, charts right ---
        split = QHBoxLayout()
        split.setSpacing(16)

        # Stage list
        stages_scroll = QScrollArea()
        stages_scroll.setWidgetResizable(True)
        stages_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        stages_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        stages_scroll.setMinimumWidth(340)
        stages_container = QWidget()
        self._stages_layout = QVBoxLayout(stages_container)
        self._stages_layout.setContentsMargins(0, 0, 0, 0)
        self._stages_layout.setSpacing(6)
        self._stages_layout.addStretch(1)
        stages_scroll.setWidget(stages_container)
        split.addWidget(stages_scroll, 1)

        # Right panel: sparkline + ticker + controls
        right_panel = QWidget()
        right_panel.setFixedWidth(300)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        right_layout.addWidget(StrongBodyLabel("Speed (c/s)"))
        self._sparkline = _SparklineWidget()
        right_layout.addWidget(self._sparkline)

        right_layout.addWidget(StrongBodyLabel("Candidates"))
        self._ticker = _CandidateTicker()
        ticker_card = CardWidget()
        ticker_inner = QVBoxLayout(ticker_card)
        ticker_inner.setContentsMargins(0, 0, 0, 0)
        ticker_inner.addWidget(self._ticker)
        right_layout.addWidget(ticker_card)

        # Control buttons
        controls = QHBoxLayout()
        self._pause_btn = PushButton("Pause")
        self._resume_btn = PushButton("Resume")
        self._cancel_btn = PushButton("Cancel")
        self._resume_btn.setVisible(False)
        self._pause_btn.clicked.connect(self._on_pause)
        self._resume_btn.clicked.connect(self._on_resume)
        self._cancel_btn.clicked.connect(self._on_cancel)
        controls.addWidget(self._pause_btn)
        controls.addWidget(self._resume_btn)
        controls.addWidget(self._cancel_btn)
        right_layout.addLayout(controls)
        right_layout.addStretch(1)

        split.addWidget(right_panel)
        root.addLayout(split, 1)

        # Found banner (hidden until password found)
        self._found_banner = QWidget()
        self._found_banner.setVisible(False)
        self._found_banner.setStyleSheet(
            "QWidget { background: #14532d; border: 1px solid #22C55E; border-radius: 8px; }"
        )
        found_layout = QHBoxLayout(self._found_banner)
        found_layout.setContentsMargins(16, 12, 16, 12)
        found_layout.setSpacing(12)
        self._found_pw_label = StrongBodyLabel("")
        self._found_pw_label.setStyleSheet(
            "font-family: 'Consolas', monospace; color: #22C55E; font-size: 16px;"
        )
        self._copy_btn = PrimaryPushButton("Copy Password")
        self._extract_btn = PrimaryPushButton("Extract Archive Now")
        self._copy_btn.clicked.connect(self._on_copy_password)
        self._extract_btn.clicked.connect(self._on_extract)
        found_layout.addWidget(BodyLabel("Password found:"))
        found_layout.addWidget(self._found_pw_label, 1)
        found_layout.addWidget(self._copy_btn)
        found_layout.addWidget(self._extract_btn)
        root.addWidget(self._found_banner)

        # Stage card registry
        self._stage_cards: dict[int, StageCard] = {}

        # Elapsed timer
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def connect_to_session(self, session_id: str, coalescer: EventCoalescer) -> None:
        """Called by main_window when a session starts."""
        self._session_id = session_id
        self._start_time = time.time()
        self._session_status = "running"
        self._found_password = None
        self._found_banner.setVisible(False)
        self._archive_label.setText("Loading…")
        self._update_status_chip("running")
        self._elapsed_timer.start()
        coalescer.events_ready.connect(self._on_events)
        self._load_session_info(session_id)

    def prepare_for_session(self, session_id: str) -> EventCoalescer:
        """Reset the page, create a fresh coalescer and return it for the caller to wire the sink."""
        from uzpr.ui.async_bridge import EventCoalescer as _EC

        # Stop any existing timer and detach old coalescer
        self._elapsed_timer.stop()
        if hasattr(self, "_coalescer") and self._coalescer is not None:
            try:
                self._coalescer.events_ready.disconnect(self._on_events)
            except RuntimeError:
                pass

        self._session_id = session_id
        self._start_time = time.time()
        self._session_status = "running"
        self._found_password = None
        self._found_banner.setVisible(False)
        self._archive_label.setText("Loading…")
        self._update_status_chip("running")
        self._pause_btn.setEnabled(True)
        self._resume_btn.setVisible(False)
        self._pause_btn.setVisible(True)

        # Reset stage cards
        for card in self._stage_cards.values():
            card.set_pending()

        self._elapsed_timer.start(1000)

        coalescer = _EC(self)
        coalescer.events_ready.connect(self._on_events)
        self._coalescer: _EC = coalescer

        self._load_session_info(session_id)
        return coalescer

    # ------------------------------------------------------------------
    # Qt lifecycle
    # ------------------------------------------------------------------

    def showEvent(self, event: object) -> None:
        super().showEvent(event)  # type: ignore[arg-type]
        if self._session_id and not self._elapsed_timer.isActive():
            self._elapsed_timer.start()

    def hideEvent(self, event: object) -> None:
        super().hideEvent(event)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def _on_events(self, batch: list[StageEvent]) -> None:
        for event in batch:
            self._process_event(event)

    def _process_event(self, event: StageEvent) -> None:
        kind = event.kind
        payload = event.payload

        if kind == "rate":
            cps: float = float(payload.get("candidates_per_sec", 0))
            self._sparkline.push(cps)
            stage_no: int | None = payload.get("stage_no")  # type: ignore[assignment]
            if stage_no is not None and stage_no in self._stage_cards:
                pct: float = float(payload.get("progress", 0))
                eta: float | None = payload.get("eta_s")  # type: ignore[assignment]
                self._stage_cards[stage_no].update_running(cps, pct, eta)
            overall = float(payload.get("overall_progress", 0))
            self._overall_progress.setValue(int(overall * 100))

        elif kind == "sample":
            candidate: str = str(payload.get("candidate", ""))
            if candidate:
                self._ticker.push(candidate)

        elif kind == "progress":
            stage_no = payload.get("stage_no")  # type: ignore[assignment]
            status: str = str(payload.get("status", ""))
            if stage_no is not None and stage_no in self._stage_cards:
                card = self._stage_cards[stage_no]
                if status == "running":
                    card.update_running(0.0, float(payload.get("progress", 0)), None)
                elif status == "found":
                    card.set_found()
                elif status == "exhausted":
                    card.set_exhausted()
                elif status == "skipped":
                    card.set_skipped()
                elif status == "failed":
                    card.set_failed()

        elif kind == "found":
            password: str = str(payload.get("password", ""))
            self._on_found(password)

        elif kind == "session_status":
            new_status: str = str(payload.get("status", ""))
            if new_status:
                self._session_status = new_status
                self._update_status_chip(new_status)

    def _on_found(self, password: str) -> None:
        self._found_password = password
        self._session_status = "found"
        self._update_status_chip("found")
        self._elapsed_timer.stop()
        self._found_pw_label.setText(password)
        self._found_banner.setVisible(True)
        self._pause_btn.setEnabled(False)
        if InfoBar is not None:
            InfoBar.success(
                title="Password Found!",
                content=f"The password is: {password}",
                parent=self,
                position=InfoBarPosition.BOTTOM_RIGHT,
                duration=8000,
            )
        # Show donation nag (skipped for Pro users and if shown today already).
        try:
            from uzpr.ui.nag import maybe_show_nag

            maybe_show_nag(parent=self)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Control buttons
    # ------------------------------------------------------------------

    def _on_pause(self) -> None:
        self._session_status = "paused"
        self._update_status_chip("paused")
        self._elapsed_timer.stop()
        self._pause_btn.setVisible(False)
        self._resume_btn.setVisible(True)

    def _on_resume(self) -> None:
        self._session_status = "running"
        self._update_status_chip("running")
        self._elapsed_timer.start()
        self._resume_btn.setVisible(False)
        self._pause_btn.setVisible(True)

    def _on_cancel(self) -> None:
        try:
            from qfluentwidgets import MessageBox  # lazy

            box = MessageBox(
                "Cancel Session",
                "Cancel this recovery session? Progress cannot be resumed.",
                self,
            )
            if box.exec():
                self._elapsed_timer.stop()
                self._session_status = "cancelled"
                self._update_status_chip("cancelled")
                self._pause_btn.setEnabled(False)
                self._resume_btn.setEnabled(False)
        except ImportError:
            from PySide6.QtWidgets import QMessageBox

            reply = QMessageBox.question(
                self,
                "Cancel Session",
                "Cancel this recovery session? Progress cannot be resumed.",
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._elapsed_timer.stop()
                self._session_status = "cancelled"
                self._update_status_chip("cancelled")

    def _on_copy_password(self) -> None:
        if self._found_password:
            QApplication.clipboard().setText(self._found_password)
            if InfoBar is not None:
                InfoBar.success(
                    title="Copied",
                    content="Password copied to clipboard.",
                    parent=self,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=2000,
                )

    def _on_extract(self) -> None:
        if not self._found_password or not self._session_id:
            return
        try:
            from PySide6.QtWidgets import QFileDialog

            dest_dir = QFileDialog.getExistingDirectory(self, "Choose extraction folder")
            if not dest_dir:
                return
            self._do_extract(Path(dest_dir))
        except Exception as exc:
            if InfoBar is not None:
                InfoBar.error(
                    title="Extraction failed",
                    content=str(exc),
                    parent=self,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=5000,
                )

    def _do_extract(self, dest: Path) -> None:
        if not self._found_password:
            return
        try:
            repo = self._app.repo
            session = repo._sync_get_session(self._session_id)  # type: ignore[arg-type]
            archive_path = Path(session.archive_path)
            import pyzipper  # type: ignore[import-untyped]

            with pyzipper.AESZipFile(archive_path) as zf:
                zf.extractall(dest, pwd=self._found_password.encode())
            if InfoBar is not None:
                InfoBar.success(
                    title="Extracted",
                    content=f"Files extracted to {dest}",
                    parent=self,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=4000,
                )
        except Exception as exc:
            if InfoBar is not None:
                InfoBar.error(
                    title="Extraction failed",
                    content=str(exc),
                    parent=self,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=5000,
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _tick_elapsed(self) -> None:
        delta = time.time() - self._start_time
        h = int(delta // 3600)
        m = int((delta % 3600) // 60)
        s = int(delta % 60)
        if h:
            self._elapsed_label.setText(f"{h}h {m:02d}m {s:02d}s")
        elif m:
            self._elapsed_label.setText(f"{m}m {s:02d}s")
        else:
            self._elapsed_label.setText(f"{s}s")

    def _update_status_chip(self, status: str) -> None:
        color = _STATUS_COLORS.get(status, "#7A7A84")
        self._status_chip.setText(status.upper())
        self._status_chip.setStyleSheet(
            f"QLabel {{ border-radius: 4px; padding: 2px 10px;"
            f" background: {color}22; color: {color}; font-size: 12px; }}"
        )

    def _load_session_info(self, session_id: str) -> None:
        try:
            repo = self._app.repo
            session = repo._sync_get_session(session_id)
            self._archive_label.setText(Path(session.archive_path).name)
            stages = repo._sync_list_stages(session_id)
            self._build_stage_cards(stages)
        except Exception:
            pass

    def _build_stage_cards(self, stages: list) -> None:
        # Remove existing cards
        while self._stages_layout.count() > 1:
            item = self._stages_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._stage_cards.clear()
        for stage in stages:
            card = StageCard(stage.stage_no, stage.name, stage.engine)
            self._stage_cards[stage.stage_no] = card
            self._stages_layout.insertWidget(self._stages_layout.count() - 1, card)
