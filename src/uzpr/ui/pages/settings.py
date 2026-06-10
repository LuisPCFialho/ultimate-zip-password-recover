from __future__ import annotations

"""Settings page — SettingCardGroup-based preferences using PyQt-Fluent-Widgets."""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from uzpr.app import AppState

import platformdirs
import psutil
from PySide6.QtWidgets import QFileDialog, QWidget
from qfluentwidgets import (
    BodyLabel,
    ComboBoxSettingCard,
    ExpandLayout,
    PrimaryPushButton,
    PushSettingCard,
    ScrollArea,
    SettingCardGroup,
    SwitchSettingCard,
    Theme,
    setTheme,
)
from qfluentwidgets import (
    FluentIcon as FIF,
)

_SETTINGS_DIR = Path(platformdirs.user_data_dir("UltimateZipPasswordRecover"))
_SETTINGS_FILE = _SETTINGS_DIR / "settings.json"

_DEFAULT_SETTINGS: dict[str, Any] = {
    "dark_mode": True,
    "gpu_low_power": False,
    "gpu_device": 0,
    "time_budget": "1h",
    "auto_resume": False,
    "auto_extract": False,
    "hashcat_path": "",
    "john_path": "",
    "bkcrack_path": "",
    "license_key": "",
}


def _load_settings() -> dict[str, Any]:
    if _SETTINGS_FILE.exists():
        try:
            with _SETTINGS_FILE.open(encoding="utf-8") as fh:
                data = json.load(fh)
            merged = dict(_DEFAULT_SETTINGS)
            merged.update(data)
            return merged
        except Exception:
            pass
    return dict(_DEFAULT_SETTINGS)


def _save_settings(settings: dict[str, Any]) -> None:
    _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    with _SETTINGS_FILE.open("w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2)


class SettingsPage(ScrollArea):
    """Full settings page built with SettingCardGroup components."""

    def __init__(self, app_state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app = app_state
        self.setObjectName("settingsPage")
        self._settings = _load_settings()
        self._build_ui()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        container = QWidget()
        container.setObjectName("settingsContainer")
        layout = ExpandLayout(container)
        layout.setContentsMargins(36, 20, 36, 36)
        layout.setSpacing(28)

        layout.addWidget(self._build_appearance_group(container))
        layout.addWidget(self._build_performance_group(container))
        layout.addWidget(self._build_recovery_group(container))
        layout.addWidget(self._build_tools_group(container))
        layout.addWidget(self._build_license_group(container))
        layout.addWidget(self._build_updates_group(container))

        self.setWidget(container)
        self.setWidgetResizable(True)

    # ------------------------------------------------------------------
    # Appearance
    # ------------------------------------------------------------------

    def _build_appearance_group(self, parent: QWidget) -> SettingCardGroup:
        group = SettingCardGroup("Appearance", parent)

        self._dark_mode_card = SwitchSettingCard(
            FIF.CONSTRACT,
            "Dark mode",
            "Toggle between dark and light theme",
            parent=group,
        )
        self._dark_mode_card.setChecked(self._settings.get("dark_mode", True))
        self._dark_mode_card.checkedChanged.connect(self._on_dark_mode_changed)

        accent_card = BodyLabel("Accent colour: Windows blue (#0078D4)", group)

        group.addSettingCard(self._dark_mode_card)
        group.addSettingCard(accent_card)
        return group

    def _on_dark_mode_changed(self, checked: bool) -> None:
        self._settings["dark_mode"] = checked
        setTheme(Theme.DARK if checked else Theme.LIGHT)
        _save_settings(self._settings)

    # ------------------------------------------------------------------
    # Performance
    # ------------------------------------------------------------------

    def _build_performance_group(self, parent: QWidget) -> SettingCardGroup:
        group = SettingCardGroup("Performance", parent)

        self._low_power_card = SwitchSettingCard(
            FIF.SPEED_OFF,
            "GPU low-power mode",
            "Reduce GPU TDP during recovery (slower but cooler)",
            parent=group,
        )
        self._low_power_card.setChecked(self._settings.get("gpu_low_power", False))
        self._low_power_card.checkedChanged.connect(self._on_low_power_changed)

        self._gpu_combo_card = ComboBoxSettingCard(
            FIF.DEVELOPER_TOOLS,
            "GPU device",
            "Select the GPU to use for hashcat attacks",
            texts=["Detecting…"],
            parent=group,
        )

        cpu_count = psutil.cpu_count(logical=True) or 1
        cpu_label = BodyLabel(f"CPU threads: {cpu_count} logical cores (psutil.cpu_count)", group)

        group.addSettingCard(self._low_power_card)
        group.addSettingCard(self._gpu_combo_card)
        group.addSettingCard(cpu_label)
        return group

    def _on_low_power_changed(self, checked: bool) -> None:
        self._settings["gpu_low_power"] = checked
        _save_settings(self._settings)

    def _on_gpu_device_changed(self, text: str) -> None:
        self._settings["gpu_device"] = text
        _save_settings(self._settings)

    # ------------------------------------------------------------------
    # Recovery
    # ------------------------------------------------------------------

    def _build_recovery_group(self, parent: QWidget) -> SettingCardGroup:
        group = SettingCardGroup("Recovery", parent)

        budget_texts = ["30min", "1h", "2h", "4h", "8h", "Custom"]
        self._budget_card = ComboBoxSettingCard(
            FIF.STOP_WATCH,
            "Default time budget",
            "Maximum wall-clock time for a single recovery session",
            texts=budget_texts,
            parent=group,
        )
        current_budget = self._settings.get("time_budget", "1h")
        if current_budget in budget_texts:
            self._budget_card.comboBox.setCurrentText(current_budget)
        self._budget_card.comboBox.currentTextChanged.connect(self._on_budget_changed)

        self._auto_resume_card = SwitchSettingCard(
            FIF.SYNC,
            "Auto-resume on launch",
            "Automatically resume the last interrupted session on startup",
            parent=group,
        )
        self._auto_resume_card.setChecked(self._settings.get("auto_resume", False))
        self._auto_resume_card.checkedChanged.connect(self._on_auto_resume_changed)

        self._auto_extract_card = SwitchSettingCard(
            FIF.UNPIN,
            "Auto-extract on success",
            "Extract archive contents automatically when the password is found",
            parent=group,
        )
        self._auto_extract_card.setChecked(self._settings.get("auto_extract", False))
        self._auto_extract_card.checkedChanged.connect(self._on_auto_extract_changed)

        group.addSettingCard(self._budget_card)
        group.addSettingCard(self._auto_resume_card)
        group.addSettingCard(self._auto_extract_card)
        return group

    def _on_budget_changed(self, text: str) -> None:
        self._settings["time_budget"] = text
        _save_settings(self._settings)

    def _on_auto_resume_changed(self, checked: bool) -> None:
        self._settings["auto_resume"] = checked
        _save_settings(self._settings)

    def _on_auto_extract_changed(self, checked: bool) -> None:
        self._settings["auto_extract"] = checked
        _save_settings(self._settings)

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    def _build_tools_group(self, parent: QWidget) -> SettingCardGroup:
        group = SettingCardGroup("Tools", parent)

        self._hashcat_card = PushSettingCard(
            "Browse",
            FIF.COMMAND_PROMPT,
            "hashcat",
            self._settings.get("hashcat_path") or "Not configured",
            group,
        )
        self._hashcat_card.clicked.connect(
            lambda: self._browse_tool("hashcat_path", self._hashcat_card)
        )

        self._john_card = PushSettingCard(
            "Browse",
            FIF.COMMAND_PROMPT,
            "John the Ripper",
            self._settings.get("john_path") or "Not configured",
            group,
        )
        self._john_card.clicked.connect(lambda: self._browse_tool("john_path", self._john_card))

        self._bkcrack_card = PushSettingCard(
            "Browse",
            FIF.COMMAND_PROMPT,
            "bkcrack",
            self._settings.get("bkcrack_path") or "Not configured",
            group,
        )
        self._bkcrack_card.clicked.connect(
            lambda: self._browse_tool("bkcrack_path", self._bkcrack_card)
        )

        self._download_btn = PrimaryPushButton("Download missing tools", group)
        self._download_btn.clicked.connect(self._on_download_tools)

        group.addSettingCard(self._hashcat_card)
        group.addSettingCard(self._john_card)
        group.addSettingCard(self._bkcrack_card)
        group.addSettingCard(self._download_btn)
        return group

    def _browse_tool(self, key: str, card: PushSettingCard) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select executable", "", "Executables (*.exe);;All files (*)"
        )
        if path:
            self._settings[key] = path
            card.setContent(path)
            _save_settings(self._settings)

    def _on_download_tools(self) -> None:
        try:
            from uzpr.engines.tool_manager import ensure_tool  # type: ignore[import]

            for tool in ("hashcat", "john", "bkcrack"):
                ensure_tool(tool)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # License
    # ------------------------------------------------------------------

    def _build_license_group(self, parent: QWidget) -> SettingCardGroup:
        from uzpr.licensing.license import load_license

        group = SettingCardGroup("License", parent)

        lic = load_license()
        if lic is not None and lic.tier == "pro":
            status_text = f"Pro — licensed to {lic.email}"
        else:
            status_text = "Free (no license)"
        self._license_label = BodyLabel(f"License status: {status_text}", group)

        activate_card = PushSettingCard(
            "Enter license key",
            FIF.CERTIFICATE,
            "License key",
            "Paste your UZPR license token to activate Pro",
            group,
        )
        activate_card.clicked.connect(self._on_activate)

        kofi_card = PushSettingCard(
            "Open Ko-fi",
            FIF.HEART,
            "Get a license",
            "Support development and receive a license key",
            group,
        )
        kofi_card.clicked.connect(self._on_open_kofi)

        group.addSettingCard(self._license_label)
        group.addSettingCard(activate_card)
        group.addSettingCard(kofi_card)
        return group

    def _on_activate(self) -> None:
        from uzpr.ui.nag import _show_license_entry  # reuse the shared entry dialog

        _show_license_entry(self)
        # Refresh status label after potential activation.
        from uzpr.licensing.license import load_license

        lic = load_license()
        if lic is not None and lic.tier == "pro":
            self._license_label.setText(f"License status: Pro — licensed to {lic.email}")
        else:
            self._license_label.setText("License status: Free (no license)")

    def _on_open_kofi(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl("https://ko-fi.com/luispcfialho"))

    # ------------------------------------------------------------------
    # Updates
    # ------------------------------------------------------------------

    def _build_updates_group(self, parent: QWidget) -> SettingCardGroup:
        group = SettingCardGroup("Updates", parent)

        update_card = PushSettingCard(
            "Check now",
            FIF.UPDATE,
            "Software updates",
            "Check GitHub for a newer version of UZPR",
            group,
        )
        update_card.clicked.connect(self._on_check_updates)

        group.addSettingCard(update_card)
        return group

    def _on_check_updates(self) -> None:
        try:
            import asyncio

            from uzpr.update.checker import check_for_updates  # type: ignore[import]

            asyncio.ensure_future(check_for_updates())
        except Exception:
            pass

    # ------------------------------------------------------------------
    # showEvent — populate GPU list
    # ------------------------------------------------------------------

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        self._populate_gpu_list()

    def _populate_gpu_list(self) -> None:
        try:
            import subprocess

            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            gpus = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        except Exception:
            gpus = []

        if not gpus:
            gpus = ["Default GPU (device 0)"]

        self._gpu_combo_card.comboBox.clear()
        self._gpu_combo_card.comboBox.addItems(gpus)

        saved = self._settings.get("gpu_device", 0)
        if isinstance(saved, int) and saved < len(gpus):
            self._gpu_combo_card.comboBox.setCurrentIndex(saved)

        self._gpu_combo_card.comboBox.currentIndexChanged.connect(
            lambda idx: self._on_gpu_device_changed(str(idx))
        )
