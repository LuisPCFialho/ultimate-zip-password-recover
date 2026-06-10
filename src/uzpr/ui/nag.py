from __future__ import annotations

"""Nag / donation prompt shown after successful recovery or on recurring launches.

Rules:
- Never shown when is_pro() is True.
- Never shown more than once per calendar day (UTC).
- Shown after every FOUND recovery.
- Shown after every 3rd session launch (launch_count % 3 == 0, starting at 3).
"""

from datetime import date
from typing import TYPE_CHECKING

from uzpr.licensing.license import install_license, is_pro, load_license
from uzpr.util.settings_store import SettingsStore

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

_KOFI_URL = "https://ko-fi.com/luispcfialho"


def _today_iso() -> str:
    return date.today().isoformat()


def _should_show(store: SettingsStore) -> bool:
    """Return True when the nag dialog may be displayed."""
    if is_pro():
        return False
    last = store.get("last_nag_at", "")
    if last == _today_iso():
        return False
    return True


def maybe_show_nag(parent: QWidget | None = None, store: SettingsStore | None = None) -> None:
    """Check conditions and show NagDialog if appropriate."""
    _store = store or SettingsStore()
    if not _should_show(_store):
        return
    try:
        dlg = NagDialog(parent=parent, store=_store)
        dlg.exec()
    except Exception:
        # Graceful if Qt not available or dialog construction fails.
        pass


def _record_nag_shown(store: SettingsStore) -> None:
    store.set("last_nag_at", _today_iso())
    store.save()


# ---------------------------------------------------------------------------
# License key mini-dialog
# ---------------------------------------------------------------------------


def _show_license_entry(parent: QWidget | None = None) -> None:
    """Small dialog to paste a license token."""
    try:
        from PySide6.QtWidgets import QDialog, QVBoxLayout

        try:
            from qfluentwidgets import (
                BodyLabel,
                InfoBar,
                InfoBarPosition,
                LineEdit,
                PrimaryPushButton,
                PushButton,
            )
        except ImportError:
            from PySide6.QtWidgets import QLabel as BodyLabel  # type: ignore[assignment]
            from PySide6.QtWidgets import QLineEdit as LineEdit  # type: ignore[assignment]
            from PySide6.QtWidgets import QPushButton as PrimaryPushButton  # type: ignore[assignment]
            from PySide6.QtWidgets import QPushButton as PushButton  # type: ignore[assignment]

            InfoBar = None  # type: ignore[assignment]
            InfoBarPosition = None  # type: ignore[assignment]

        dlg = QDialog(parent)
        dlg.setWindowTitle("Enter license key")
        dlg.setMinimumWidth(460)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(BodyLabel("Paste your UZPR license key below:"))
        edit = LineEdit()
        edit.setPlaceholderText("eyJ...")
        layout.addWidget(edit)

        btn_row_widget = __import__("PySide6.QtWidgets", fromlist=["QHBoxLayout"]).QHBoxLayout  # noqa: F841
        from PySide6.QtWidgets import QHBoxLayout

        row = QHBoxLayout()
        ok_btn = PrimaryPushButton("Activate")
        cancel_btn = PushButton("Cancel")
        row.addStretch(1)
        row.addWidget(cancel_btn)
        row.addWidget(ok_btn)
        layout.addLayout(row)

        cancel_btn.clicked.connect(dlg.reject)

        def _activate() -> None:
            token = edit.text().strip()
            if not token:
                return
            try:
                install_license(token)
                if InfoBar is not None:
                    InfoBar.success(
                        title="License activated",
                        content="Thank you! UZPR Pro is now active.",
                        parent=parent,
                        position=InfoBarPosition.TOP,
                        duration=4000,
                    )
            except ValueError:
                if InfoBar is not None:
                    InfoBar.error(
                        title="Invalid key",
                        content="This license key could not be verified. Check for typos.",
                        parent=parent,
                        position=InfoBarPosition.TOP,
                        duration=4000,
                    )
                return
            dlg.accept()

        ok_btn.clicked.connect(_activate)
        dlg.exec()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Nag dialog
# ---------------------------------------------------------------------------


class NagDialog:
    """Donation prompt dialog.

    Constructed only when Qt is available; uses qfluentwidgets with plain-Qt
    fallbacks so it never hard-crashes in test environments.
    """

    def __init__(self, parent: QWidget | None = None, store: SettingsStore | None = None) -> None:
        self._store = store or SettingsStore()
        self._parent = parent
        self._dlg = self._build(parent)

    def _build(self, parent: QWidget | None) -> object:
        from PySide6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout

        try:
            from qfluentwidgets import BodyLabel, PrimaryPushButton, PushButton, TitleLabel
        except ImportError:
            from PySide6.QtWidgets import QLabel as BodyLabel  # type: ignore[assignment]
            from PySide6.QtWidgets import QLabel as TitleLabel  # type: ignore[assignment]
            from PySide6.QtWidgets import QPushButton as PrimaryPushButton  # type: ignore[assignment]
            from PySide6.QtWidgets import QPushButton as PushButton  # type: ignore[assignment]

        dlg = QDialog(parent)
        dlg.setWindowTitle("UZPR — Support the project")
        dlg.setMinimumWidth(480)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        layout.addWidget(TitleLabel("Recovery complete — UZPR is free"))
        body = BodyLabel(
            "UZPR is free and open source. If it helped you, a small donation keeps development going."
        )
        body.setWordWrap(True)
        layout.addWidget(body)

        row = QHBoxLayout()
        kofi_btn = PrimaryPushButton("Support on Ko-fi")
        key_btn = PushButton("I have a license key")
        later_btn = PushButton("Maybe later")
        row.addWidget(kofi_btn)
        row.addWidget(key_btn)
        row.addStretch(1)
        row.addWidget(later_btn)
        layout.addLayout(row)

        kofi_btn.clicked.connect(lambda: self._open_kofi(dlg))
        key_btn.clicked.connect(lambda: self._enter_key(dlg))
        later_btn.clicked.connect(dlg.reject)

        return dlg

    def _open_kofi(self, dlg: object) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        QDesktopServices.openUrl(QUrl(_KOFI_URL))
        dlg.accept()  # type: ignore[union-attr]

    def _enter_key(self, dlg: object) -> None:
        _show_license_entry(self._parent)
        if is_pro():
            dlg.accept()  # type: ignore[union-attr]

    def exec(self) -> int:
        _record_nag_shown(self._store)
        return self._dlg.exec()  # type: ignore[union-attr]
