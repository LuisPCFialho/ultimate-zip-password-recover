from __future__ import annotations

"""History page — filterable table of past sessions with detail dialog."""

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from qfluentwidgets import (
        BodyLabel,
        CaptionLabel,
        InfoBar,
        InfoBarPosition,
        MessageBox,
        PushButton,
        SearchLineEdit,
        TableWidget,
        TitleLabel,
        ToolButton,
    )
    try:
        from qfluentwidgets import FluentIcon as FIF
        _HAS_FIF = True
    except ImportError:
        _HAS_FIF = False
except ImportError:
    from PySide6.QtWidgets import QLabel as BodyLabel  # type: ignore[assignment]
    from PySide6.QtWidgets import QLabel as CaptionLabel  # type: ignore[assignment]
    InfoBar = None  # type: ignore[assignment,misc]
    InfoBarPosition = None  # type: ignore[assignment,misc]
    MessageBox = None  # type: ignore[assignment,misc]
    from PySide6.QtWidgets import QLabel as TitleLabel  # type: ignore[assignment]
    from PySide6.QtWidgets import QLineEdit as SearchLineEdit  # type: ignore[assignment]
    from PySide6.QtWidgets import QPushButton as PushButton  # type: ignore[assignment]
    from PySide6.QtWidgets import QPushButton as ToolButton  # type: ignore[assignment]
    from PySide6.QtWidgets import QTableWidget as TableWidget  # type: ignore[assignment]
    _HAS_FIF = False

if TYPE_CHECKING:
    from uzpr.persistence.models import SessionRow

_COL_ARCHIVE  = 0
_COL_FORMAT   = 1
_COL_STATUS   = 2
_COL_PASSWORD = 3
_COL_STAGE    = 4
_COL_DURATION = 5
_COL_DATE     = 6
_COL_COUNT    = 7

_HEADERS = ["Archive", "Format", "Status", "Password", "Found By", "Duration", "Date"]

_STATUS_COLORS: dict[str, str] = {
    "pending":   "#7A7A84",
    "running":   "#3B82F6",
    "paused":    "#F59E0B",
    "found":     "#22C55E",
    "exhausted": "#F97316",
    "cancelled": "#EF4444",
    "failed":    "#EF4444",
}


def _fmt_duration(start: float, end: float) -> str:
    delta = max(0.0, end - start)
    h = int(delta // 3600)
    m = int((delta % 3600) // 60)
    s = int(delta % 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def _fmt_date(ts: float) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


class _PasswordCell(QWidget):
    """Table cell that shows a masked password with an eye-toggle button."""

    def __init__(self, password: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._password = password
        self._visible = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(6)

        self._label = BodyLabel("••••••" if password else "—")
        self._label.setStyleSheet(
            "font-family: 'Consolas', monospace; color: #B4B4BC;"
        )

        self._toggle_btn = PushButton("Show")
        self._toggle_btn.setFixedSize(48, 22)
        self._toggle_btn.setVisible(bool(password))
        self._toggle_btn.clicked.connect(self._toggle)

        layout.addWidget(self._label, 1)
        layout.addWidget(self._toggle_btn)

    def _toggle(self) -> None:
        self._visible = not self._visible
        if self._visible:
            self._label.setText(self._password)
            self._toggle_btn.setText("Hide")
        else:
            self._label.setText("••••••")
            self._toggle_btn.setText("Show")


class HistoryPage(QWidget):
    """Filterable history of all past recovery sessions."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("historyPage")

        self._all_sessions: list[SessionRow] = []
        self._password_map: dict[str, str] = {}  # session_id -> password

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        # --- Top bar: title + search + clear ---
        top_row = QHBoxLayout()
        top_row.addWidget(TitleLabel("History"))
        top_row.addStretch(1)

        self._search = SearchLineEdit()
        self._search.setPlaceholderText("Filter by filename…")
        self._search.setFixedWidth(260)
        self._search.textChanged.connect(self._apply_filter)
        top_row.addWidget(self._search)

        self._clear_btn = ToolButton()
        try:
            if _HAS_FIF:
                self._clear_btn.setIcon(FIF.DELETE)
        except Exception:
            pass
        self._clear_btn.setToolTip("Clear history")
        self._clear_btn.clicked.connect(self._on_clear_history)
        top_row.addWidget(self._clear_btn)

        root.addLayout(top_row)

        # --- Table ---
        self._table = TableWidget()
        self._table.setColumnCount(_COL_COUNT)
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(TableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(
            _COL_ARCHIVE, QHeaderView.ResizeMode.Stretch
        )
        self._table.horizontalHeader().setSectionResizeMode(
            _COL_PASSWORD, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.verticalHeader().setVisible(False)
        self._table.doubleClicked.connect(self._on_row_double_click)
        root.addWidget(self._table, 1)

        # Row count label
        self._count_label = CaptionLabel("0 sessions")
        self._count_label.setStyleSheet("color: #7A7A84;")
        root.addWidget(self._count_label)

    # ------------------------------------------------------------------
    # Qt lifecycle
    # ------------------------------------------------------------------

    def showEvent(self, event: object) -> None:
        super().showEvent(event)  # type: ignore[arg-type]
        self._load_sessions()

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_sessions(self) -> None:
        try:
            import asyncio

            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self._async_load())
            else:
                self._sync_load()
        except Exception:
            self._sync_load()

    def _sync_load(self) -> None:
        try:
            from uzpr.app import build_application  # lazy

            app = build_application()
            repo = app._repo  # type: ignore[attr-defined]
            sessions = repo._sync_list_sessions(None)
            sessions.sort(key=lambda s: s.updated_at, reverse=True)
            self._all_sessions = sessions
            self._load_passwords(repo, sessions)
            self._apply_filter(self._search.text())
        except Exception:
            pass

    async def _async_load(self) -> None:
        try:
            from uzpr.app import build_application  # lazy

            app = build_application()
            repo = app._repo  # type: ignore[attr-defined]
            sessions = await repo.list_sessions()
            sessions.sort(key=lambda s: s.updated_at, reverse=True)
            self._all_sessions = sessions
            self._load_passwords(repo, sessions)
            self._apply_filter(self._search.text())
        except Exception:
            pass

    def _load_passwords(self, repo: object, sessions: list[SessionRow]) -> None:
        self._password_map.clear()
        try:
            for session in sessions:
                if session.status == "found":
                    row = repo._conn.execute(  # type: ignore[attr-defined]
                        "SELECT password FROM results WHERE session_id = ? LIMIT 1",
                        (session.id,),
                    ).fetchone()
                    if row:
                        self._password_map[session.id] = row["password"]
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Table population
    # ------------------------------------------------------------------

    def _apply_filter(self, text: str) -> None:
        query = text.strip().lower()
        filtered = [
            s for s in self._all_sessions
            if not query or query in Path(s.archive_path).name.lower()
        ]
        self._populate_table(filtered)

    def _populate_table(self, sessions: list[SessionRow]) -> None:
        self._table.setRowCount(0)
        self._table.setRowCount(len(sessions))

        for row, session in enumerate(sessions):
            archive_name = Path(session.archive_path).name
            self._table.setItem(row, _COL_ARCHIVE, QTableWidgetItem(archive_name))
            self._table.setItem(row, _COL_FORMAT,  QTableWidgetItem(session.archive_format))

            status_item = QTableWidgetItem(session.status.upper())
            color = _STATUS_COLORS.get(session.status, "#7A7A84")
            from PySide6.QtGui import QColor
            status_item.setForeground(QColor(color))
            self._table.setItem(row, _COL_STATUS, status_item)

            password = self._password_map.get(session.id, "")
            pw_widget = _PasswordCell(password)
            self._table.setCellWidget(row, _COL_PASSWORD, pw_widget)

            self._table.setItem(row, _COL_STAGE, QTableWidgetItem("—"))

            duration = _fmt_duration(session.created_at, session.updated_at)
            self._table.setItem(row, _COL_DURATION, QTableWidgetItem(duration))

            date_str = _fmt_date(session.created_at)
            self._table.setItem(row, _COL_DATE, QTableWidgetItem(date_str))

            # Store session_id in the archive item for retrieval on double-click
            item = self._table.item(row, _COL_ARCHIVE)
            if item:
                item.setData(Qt.ItemDataRole.UserRole, session.id)

        self._table.resizeRowsToContents()
        n = len(sessions)
        self._count_label.setText(f"{n} session{'s' if n != 1 else ''}")

    # ------------------------------------------------------------------
    # Interactions
    # ------------------------------------------------------------------

    def _on_row_double_click(self, index: object) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        archive_item = self._table.item(row, _COL_ARCHIVE)
        if archive_item is None:
            return
        session_id: str = archive_item.data(Qt.ItemDataRole.UserRole)
        if not session_id:
            return
        self._show_detail_dialog(session_id)

    def _show_detail_dialog(self, session_id: str) -> None:
        try:
            from uzpr.app import build_application  # lazy

            app = build_application()
            repo = app._repo  # type: ignore[attr-defined]
            session = repo._sync_get_session(session_id)
            stages = repo._sync_list_stages(session_id)
            password = self._password_map.get(session_id, "—")
            duration = _fmt_duration(session.created_at, session.updated_at)
            date_str = _fmt_date(session.created_at)

            lines = [
                f"Archive: {session.archive_path}",
                f"Format: {session.archive_format}",
                f"Status: {session.status}",
                f"Password: {password}",
                f"Duration: {duration}",
                f"Date: {date_str}",
                f"Budget: {session.total_budget_s:.0f}s",
                "",
                "Stages:",
            ]
            for stage in stages:
                lines.append(
                    f"  #{stage.stage_no} {stage.name} [{stage.engine}] → {stage.status}"
                    f"  ({stage.candidates_tested:,} candidates, {stage.elapsed_s:.1f}s)"
                )

            detail_text = "\n".join(lines)

            if MessageBox is not None:
                box = MessageBox(
                    Path(session.archive_path).name,
                    detail_text,
                    self,
                )
                box.exec()
            else:
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.information(
                    self,
                    Path(session.archive_path).name,
                    detail_text,
                )
        except Exception as exc:
            if InfoBar is not None:
                InfoBar.error(
                    title="Error loading session",
                    content=str(exc),
                    parent=self,
                    position=InfoBarPosition.TOP,
                    duration=4000,
                )

    def _on_clear_history(self) -> None:
        confirmed = False
        try:
            if MessageBox is not None:
                box = MessageBox(
                    "Clear History",
                    "Delete all session history? This cannot be undone.",
                    self,
                )
                confirmed = bool(box.exec())
            else:
                from PySide6.QtWidgets import QMessageBox

                reply = QMessageBox.question(
                    self,
                    "Clear History",
                    "Delete all session history? This cannot be undone.",
                )
                confirmed = reply == QMessageBox.StandardButton.Yes
        except Exception:
            return

        if not confirmed:
            return

        try:
            from uzpr.app import build_application  # lazy

            app = build_application()
            repo = app._repo  # type: ignore[attr-defined]
            repo._conn.execute("DELETE FROM sessions")
            repo._conn.execute("DELETE FROM stages")
            repo._conn.execute("DELETE FROM results")
            repo._conn.execute("DELETE FROM events")
            repo._conn.execute("DELETE FROM attempts")
            repo._conn.commit()
            self._all_sessions = []
            self._password_map.clear()
            self._table.setRowCount(0)
            self._count_label.setText("0 sessions")
            if InfoBar is not None:
                InfoBar.success(
                    title="History cleared",
                    content="All session records have been deleted.",
                    parent=self,
                    position=InfoBarPosition.BOTTOM_RIGHT,
                    duration=3000,
                )
        except Exception as exc:
            if InfoBar is not None:
                InfoBar.error(
                    title="Error",
                    content=str(exc),
                    parent=self,
                    position=InfoBarPosition.TOP,
                    duration=4000,
                )
