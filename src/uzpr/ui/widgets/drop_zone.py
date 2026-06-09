from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QMouseEvent
from PySide6.QtWidgets import QFileDialog, QLabel, QWidget

_VALID_EXTENSIONS = {".zip", ".rar"}

_STYLE_NORMAL = """
    QLabel {
        border: 2px dashed #3B82F6;
        border-radius: 12px;
        background: transparent;
        color: #B4B4BC;
        font-size: 14px;
        padding: 40px;
    }
    QLabel:hover {
        border-color: #60A5FA;
        color: #E8E8EE;
        background: rgba(59, 130, 246, 0.06);
    }
"""

_STYLE_DRAG_OVER = """
    QLabel {
        border: 2px dashed #60A5FA;
        border-radius: 12px;
        background: rgba(59, 130, 246, 0.12);
        color: #E8E8EE;
        font-size: 14px;
        padding: 40px;
    }
"""


class DropZone(QLabel):
    """Drag-and-drop zone that emits file_dropped(Path) when a valid archive is dropped."""

    file_dropped: Signal = Signal(Path)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(180)
        self.setStyleSheet(_STYLE_NORMAL)
        self.setText(
            "\U0001f5c2\n\nDrop a ZIP or RAR archive here\nor click to browse"
        )
        self.setWordWrap(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        mime = event.mimeData()
        if mime.hasUrls():
            urls = mime.urls()
            if urls and Path(urls[0].toLocalFile()).suffix.lower() in _VALID_EXTENSIONS:
                event.acceptProposedAction()
                self.setStyleSheet(_STYLE_DRAG_OVER)
                return
        event.ignore()

    def dragLeaveEvent(self, event: object) -> None:
        self.setStyleSheet(_STYLE_NORMAL)

    def dropEvent(self, event: QDropEvent) -> None:
        self.setStyleSheet(_STYLE_NORMAL)
        mime = event.mimeData()
        if not mime.hasUrls():
            return
        urls = mime.urls()
        if not urls:
            return
        local = urls[0].toLocalFile()
        path = Path(local)
        if path.suffix.lower() not in _VALID_EXTENSIONS:
            return
        event.acceptProposedAction()
        self.file_dropped.emit(path)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Select Archive",
            "",
            "Archive files (*.zip *.rar);;All files (*)",
        )
        if path_str:
            self.file_dropped.emit(Path(path_str))
