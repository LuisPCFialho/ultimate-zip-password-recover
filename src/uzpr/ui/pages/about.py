from __future__ import annotations

"""About page — version info, GitHub link, license notice, credits."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    HyperlinkButton,
    ScrollArea,
    TitleLabel,
)

import uzpr


class AboutPage(ScrollArea):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("aboutPage")
        self._build_ui()

    def _build_ui(self) -> None:
        container = QWidget()
        container.setObjectName("aboutContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 32, 36, 36)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # --- Version card ---
        version_card = CardWidget(container)
        card_layout = QVBoxLayout(version_card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(8)

        title = TitleLabel("Ultimate ZIP Password Recover", version_card)
        version_label = BodyLabel(f"Version {uzpr.__version__}", version_card)
        description = BodyLabel(
            "Intelligent, stage-based password recovery for encrypted ZIP and RAR archives.",
            version_card,
        )
        description.setWordWrap(True)

        card_layout.addWidget(title)
        card_layout.addWidget(version_label)
        card_layout.addWidget(description)

        github_btn = HyperlinkButton(
            "https://github.com/LuisPCFialho/ultimate-zip-password-recover",
            "View on GitHub",
            version_card,
        )
        card_layout.addWidget(github_btn)

        layout.addWidget(version_card)

        # --- License card ---
        license_card = CardWidget(container)
        lic_layout = QVBoxLayout(license_card)
        lic_layout.setContentsMargins(24, 20, 24, 20)
        lic_layout.setSpacing(6)

        lic_title = BodyLabel("License", license_card)
        lic_title.setObjectName("licSectionTitle")
        lic_body = BodyLabel(
            "This application is released under the MIT License.\n"
            "See LICENSE in the source repository for the full text.",
            license_card,
        )
        lic_body.setWordWrap(True)

        lic_layout.addWidget(lic_title)
        lic_layout.addWidget(lic_body)
        layout.addWidget(license_card)

        # --- Credits card ---
        credits_card = CardWidget(container)
        cred_layout = QVBoxLayout(credits_card)
        cred_layout.setContentsMargins(24, 20, 24, 20)
        cred_layout.setSpacing(6)

        cred_title = BodyLabel("Credits", credits_card)
        cred_title.setObjectName("credSectionTitle")
        cred_body = BodyLabel(
            "Powered by hashcat, John the Ripper, bkcrack.\n"
            "UI built with PyQt-Fluent-Widgets (GPLv3) and PySide6 (LGPL).\n"
            "Icons from Fluent UI System Icons (MIT).",
            credits_card,
        )
        cred_body.setWordWrap(True)

        cred_layout.addWidget(cred_title)
        cred_layout.addWidget(cred_body)
        layout.addWidget(credits_card)

        layout.addStretch()

        self.setWidget(container)
        self.setWidgetResizable(True)
