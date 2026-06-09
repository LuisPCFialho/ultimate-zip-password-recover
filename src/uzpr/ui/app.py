from __future__ import annotations

"""GUI entry point called from uzpr.__main__.run_gui()."""

import asyncio

import qasync
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication


def run_gui(argv: list[str]) -> int:
    """Create QApplication, apply theme, show main window, run event loop."""
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(argv)
    app.setApplicationName("Ultimate ZIP Password Recover")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("UZPR")

    from uzpr.ui.theme import apply_theme, load_fonts

    # Architecture spec: Theme.AUTO at startup
    apply_theme(dark=None)
    load_fonts()

    from uzpr.ui.main_window import MainWindow

    window = MainWindow()
    window.show()

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    with loop:
        return loop.run_forever()
