from __future__ import annotations

"""Main application window using PyQt-Fluent-Widgets FluentWindow."""

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import FluentWindow, NavigationItemPosition

from uzpr.app import AppState
from uzpr.ui.pages.about import AboutPage
from uzpr.ui.pages.active_jobs import ActiveJobsPage
from uzpr.ui.pages.history import HistoryPage
from uzpr.ui.pages.home import HomePage
from uzpr.ui.pages.new_job_wizard import NewJobWizardPage
from uzpr.ui.pages.settings import SettingsPage
from uzpr.ui.wizard import WizardWindow


class MainWindow(FluentWindow):
    def __init__(self, app_state: AppState) -> None:
        super().__init__()
        self.app_state = app_state
        self._init_window()
        self._init_navigation()

    def _init_window(self) -> None:
        self.setWindowTitle("Ultimate ZIP Password Recover")
        self.resize(1100, 750)
        self.setMinimumSize(QSize(900, 600))

        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(
                geo.center().x() - self.width() // 2,
                geo.center().y() - self.height() // 2,
            )

    def _init_navigation(self) -> None:
        self.home_page = HomePage(self.app_state, self)
        self.new_job_page = WizardWindow(self.app_state, self)
        self.new_job_page.setObjectName("newJobWizardPage")
        self.active_page = ActiveJobsPage(self.app_state, self)
        self.history_page = HistoryPage(self.app_state, self)
        self.settings_page = SettingsPage(self.app_state, self)
        self.about_page = AboutPage(self)

        # Main rail — top section
        self.addSubInterface(self.home_page, FIF.HOME, "Home")
        self.addSubInterface(self.new_job_page, FIF.ADD, "New Job")
        # Architecture spec uses FIF.PLAY for Active Jobs
        self.addSubInterface(self.active_page, FIF.PLAY, "Active Jobs")
        self.addSubInterface(self.history_page, FIF.HISTORY, "History")

        # Bottom rail
        self.addSubInterface(
            self.settings_page,
            FIF.SETTING,
            "Settings",
            position=NavigationItemPosition.BOTTOM,
        )
        self.addSubInterface(
            self.about_page,
            FIF.INFO,
            "About",
            position=NavigationItemPosition.BOTTOM,
        )

        self.navigationInterface.setCurrentItem(self.home_page.objectName())

        # Wire cross-page navigation
        self.home_page.file_selected.connect(self._on_file_selected)
        self.home_page.session_clicked.connect(self._on_session_clicked)
        self.new_job_page.session_started.connect(self._on_session_started)

    # ------------------------------------------------------------------
    # Navigation handlers
    # ------------------------------------------------------------------

    def _on_file_selected(self, path: object) -> None:
        from pathlib import Path

        self.new_job_page.set_archive(Path(str(path)))
        self.switchTo(self.new_job_page)

    def _on_session_clicked(self, session_id: str) -> None:
        """Navigate to active page if session is running, else history."""
        if self.active_page._session_id == session_id:
            self.switchTo(self.active_page)
        else:
            self.switchTo(self.history_page)

    def _on_session_started(self, session_id: str) -> None:
        import asyncio

        from uzpr.ui.async_bridge import make_event_sink

        coalescer = self.active_page.prepare_for_session(session_id)
        self.switchTo(self.active_page)

        sink = make_event_sink(coalescer)
        asyncio.ensure_future(self.app_state.orchestrator.run_session(session_id, sink))
