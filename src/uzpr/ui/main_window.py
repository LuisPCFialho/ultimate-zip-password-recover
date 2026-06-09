from __future__ import annotations

"""Main application window using PyQt-Fluent-Widgets FluentWindow."""

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import FluentWindow, NavigationItemPosition

from uzpr.ui.pages.active_jobs import ActiveJobsPage
from uzpr.ui.pages.history import HistoryPage
from uzpr.ui.pages.home import HomePage
from uzpr.ui.pages.new_job_wizard import NewJobWizardPage
from uzpr.ui.pages.settings import SettingsPage


class MainWindow(FluentWindow):
    def __init__(self) -> None:
        super().__init__()
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
        self.home_page = HomePage(self)
        self.new_job_page = NewJobWizardPage(self)
        self.active_page = ActiveJobsPage(self)
        self.history_page = HistoryPage(self)
        self.settings_page = SettingsPage(self)

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

        self.navigationInterface.setCurrentItem(self.home_page.objectName())
