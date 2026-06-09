from __future__ import annotations

"""New Job Wizard — multi-step setup page embedded in the navigation."""

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

try:
    from qfluentwidgets import (
        BodyLabel,
        CaptionLabel,
        CardWidget,
        ComboBox,
        InfoBar,
        InfoBarPosition,
        LineEdit,
        PrimaryPushButton,
        PushButton,
        StrongBodyLabel,
        SubtitleLabel,
    )
except ImportError:
    from PySide6.QtWidgets import QComboBox as ComboBox  # type: ignore[assignment]
    from PySide6.QtWidgets import QFrame as CardWidget  # type: ignore[assignment]
    from PySide6.QtWidgets import QLabel as BodyLabel  # type: ignore[assignment]
    from PySide6.QtWidgets import QLabel as CaptionLabel  # type: ignore[assignment]

    InfoBar = None  # type: ignore[assignment,misc]
    InfoBarPosition = None  # type: ignore[assignment,misc]
    from PySide6.QtWidgets import QLabel as StrongBodyLabel  # type: ignore[assignment]
    from PySide6.QtWidgets import QLabel as SubtitleLabel  # type: ignore[assignment]
    from PySide6.QtWidgets import QLineEdit as LineEdit  # type: ignore[assignment]
    from PySide6.QtWidgets import QPushButton as PrimaryPushButton  # type: ignore[assignment]
    from PySide6.QtWidgets import QPushButton as PushButton  # type: ignore[assignment]

if TYPE_CHECKING:
    from uzpr.archive.detect import ArchiveInfo

_BUDGET_OPTIONS: list[tuple[str, int]] = [
    ("1 min", 60),
    ("5 min", 300),
    ("30 min", 1800),
    ("2 h", 7200),
    ("8 h", 28800),
    ("24 h", 86400),
]

_STAGE_TABLE: list[tuple[int, str, str, str, str]] = [
    (1, "known-password", "native", "100%", "free"),
    (2, "partial-mask", "hashcat", "70%", "free"),
    (3, "generated-wordlist", "hashcat", "40%", "free"),
    (4, "rockyou-straight", "hashcat", "35%", "1/9"),
    (5, "rockyou-rules", "hashcat", "30%", "1/9"),
    (6, "masks-brute", "hashcat", "25%", "1/9"),
    (7, "prince-stems", "hashcat", "20%", "1/9"),
    (8, "john-incremental", "john", "15%", "1/9"),
    (9, "hybrid-wl-mask", "hashcat", "12%", "1/9"),
    (10, "hybrid-mask-wl", "hashcat", "10%", "1/9"),
    (11, "combinator", "hashcat", "8%", "1/9"),
    (12, "targeted-brute", "hashcat", "6%", "1/9"),
    (13, "bkcrack-plaintext", "bkcrack", "100%", "free"),
]


def _make_separator() -> QWidget:
    sep = QWidget()
    sep.setFixedHeight(1)
    sep.setStyleSheet("background: #2B2B33;")
    return sep


def _section_title(text: str) -> QLabel:
    lbl = StrongBodyLabel(text)
    lbl.setStyleSheet("color: #B4B4BC; margin-top: 8px;")
    return lbl


# ---------------------------------------------------------------------------
# Step pages
# ---------------------------------------------------------------------------


class _StepArchive(QWidget):
    """Step 1 — archive selection and detection."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(SubtitleLabel("Select Archive"))

        # Path display
        path_row = QHBoxLayout()
        self._path_label = LineEdit()
        self._path_label.setPlaceholderText("No archive selected")
        self._path_label.setReadOnly(True)
        self._browse_btn = PushButton("Browse…")
        path_row.addWidget(self._path_label, 1)
        path_row.addWidget(self._browse_btn)
        layout.addLayout(path_row)

        self._detect_btn = PrimaryPushButton("Detect Format")
        self._detect_btn.setEnabled(False)
        layout.addWidget(self._detect_btn)

        # Info card
        self._info_card = CardWidget()
        info_layout = QVBoxLayout(self._info_card)
        info_layout.setContentsMargins(16, 14, 16, 14)
        info_layout.setSpacing(6)
        self._info_format = BodyLabel("Format: —")
        self._info_entries = BodyLabel("Entries: —")
        self._info_encryption = BodyLabel("Encryption: —")
        self._info_recommended = BodyLabel("Recommended attack: —")
        for lbl in (
            self._info_format,
            self._info_entries,
            self._info_encryption,
            self._info_recommended,
        ):
            info_layout.addWidget(lbl)
        self._info_card.setVisible(False)
        layout.addWidget(self._info_card)

        layout.addStretch(1)

        self._browse_btn.clicked.connect(self._on_browse)
        self._detect_btn.clicked.connect(self._on_detect)

        self._archive_info: ArchiveInfo | None = None

    def set_archive(self, path: Path) -> None:
        self._path_label.setText(str(path))
        self._detect_btn.setEnabled(True)
        self._archive_info = None
        self._info_card.setVisible(False)
        self._on_detect()

    def get_archive_info(self) -> ArchiveInfo | None:
        return self._archive_info

    def _on_browse(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Select Archive",
            "",
            "Archive files (*.zip *.rar);;All files (*)",
        )
        if path_str:
            self.set_archive(Path(path_str))

    def _on_detect(self) -> None:
        path_str = self._path_label.text().strip()
        if not path_str:
            return
        path = Path(path_str)
        if not path.exists():
            self._show_error("File not found.")
            return
        try:
            from uzpr.archive.detect import detect_archive  # lazy

            info = detect_archive(path)
            self._archive_info = info
            self._info_format.setText(f"Format: {info.format}")
            self._info_entries.setText(f"Entries: {len(info.entries)}")
            enc = (
                f"AES-{info.aes_strength}"
                if info.aes_strength
                else ("Header-encrypted" if info.header_encrypted else "Standard")
            )
            self._info_encryption.setText(f"Encryption: {enc}")
            mode_map = {
                "zip-classic": "ZipCrypto (mode 17200/17225)",
                "zip-aes": "WinZip-AES (mode 13600)",
                "rar3-hp": "RAR3 (mode 12500)",
                "rar5": "RAR5 (mode 13000)",
            }
            rec = mode_map.get(info.format, "Unknown — check manually")
            self._info_recommended.setText(f"Recommended attack: {rec}")
            self._info_card.setVisible(True)

            if info.format == "pkware-strong":
                self._show_warning(
                    "PKWARE Strong Encryption is not recoverable by brute-force. Proceed only if you have a known-password hint."
                )
        except Exception as exc:
            self._show_error(f"Detection failed: {exc}")

    def _show_error(self, msg: str) -> None:
        if InfoBar is not None:
            InfoBar.error(
                title="Error",
                content=msg,
                parent=self,
                position=InfoBarPosition.TOP,
                duration=4000,
            )

    def _show_warning(self, msg: str) -> None:
        if InfoBar is not None:
            InfoBar.warning(
                title="Warning",
                content=msg,
                parent=self,
                position=InfoBarPosition.TOP,
                duration=6000,
            )


class _StepHints(QWidget):
    """Step 2 — hints intake form."""

    candidate_count_changed: Signal = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(SubtitleLabel("Hints"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        inner = QWidget()
        form = QVBoxLayout(inner)
        form.setContentsMargins(0, 8, 0, 8)
        form.setSpacing(12)

        # --- Dates ---
        form.addWidget(_section_title("Dates"))
        self._date_rows: list[tuple[QDateEdit, ComboBox]] = []
        self._dates_container = QVBoxLayout()
        self._dates_container.setSpacing(6)
        form.addLayout(self._dates_container)
        add_date_btn = PushButton("+ Add Date")
        add_date_btn.clicked.connect(self._add_date_row)
        form.addWidget(add_date_btn)
        self._add_date_row()

        form.addWidget(_make_separator())

        # --- Names ---
        form.addWidget(_section_title("Names"))
        self._first_names: list[LineEdit] = []
        self._surnames: list[LineEdit] = []
        self._nicknames: list[LineEdit] = []
        self._pet_names: list[LineEdit] = []
        self._children_names: list[LineEdit] = []
        name_form = QFormLayout()
        name_form.setSpacing(8)
        for label, store in (
            ("First names (comma-sep)", self._first_names),
            ("Surnames", self._surnames),
            ("Nicknames", self._nicknames),
            ("Pet names", self._pet_names),
            ("Children names", self._children_names),
        ):
            edit = LineEdit()
            edit.setPlaceholderText(label)
            edit.textChanged.connect(self._on_hint_changed)
            store.append(edit)
            name_form.addRow(BodyLabel(label + ":"), edit)
        form.addLayout(name_form)

        form.addWidget(_make_separator())

        # --- Places ---
        form.addWidget(_section_title("Places"))
        self._place_edits: list[LineEdit] = []
        places_layout = QVBoxLayout()
        places_layout.setSpacing(6)
        for placeholder in ("City / town", "Country", "Street / suburb", "Other place"):
            edit = LineEdit()
            edit.setPlaceholderText(placeholder)
            edit.textChanged.connect(self._on_hint_changed)
            self._place_edits.append(edit)
            places_layout.addWidget(edit)
        form.addLayout(places_layout)

        form.addWidget(_make_separator())

        # --- Stems ---
        form.addWidget(_section_title("Stems (comma-separated keywords)"))
        self._stems_edit = LineEdit()
        self._stems_edit.setPlaceholderText("e.g. summer, holiday, work")
        self._stems_edit.textChanged.connect(self._on_hint_changed)
        form.addWidget(self._stems_edit)

        form.addWidget(_make_separator())

        # --- Suffix / Prefix habits ---
        form.addWidget(_section_title("Common suffix / prefix patterns"))
        self._suffix_checks: dict[str, QCheckBox] = {}
        sfx_layout = QHBoxLayout()
        sfx_layout.setSpacing(8)
        for tag in ("123", "!", "1", "2023", "2024", "2025", "#", "@"):
            cb = QCheckBox(tag)
            cb.stateChanged.connect(self._on_hint_changed)
            self._suffix_checks[tag] = cb
            sfx_layout.addWidget(cb)
        sfx_layout.addStretch(1)
        form.addLayout(sfx_layout)

        form.addWidget(_make_separator())

        # --- Charset hints ---
        form.addWidget(_section_title("Character set hints"))
        charset_layout = QHBoxLayout()
        charset_layout.setSpacing(16)
        self._cb_upper = QCheckBox("Uppercase (A-Z)")
        self._cb_lower = QCheckBox("Lowercase (a-z)")
        self._cb_digit = QCheckBox("Digits (0-9)")
        self._cb_symbol = QCheckBox("Symbols (!@#…)")
        for cb in (self._cb_upper, self._cb_lower, self._cb_digit, self._cb_symbol):
            cb.setChecked(True)
            cb.stateChanged.connect(self._on_hint_changed)
            charset_layout.addWidget(cb)
        charset_layout.addStretch(1)
        form.addLayout(charset_layout)

        form.addWidget(_make_separator())

        # --- Length range ---
        form.addWidget(_section_title("Password length range"))
        length_layout = QHBoxLayout()
        length_layout.setSpacing(12)
        self._min_slider = QSlider(Qt.Orientation.Horizontal)
        self._min_slider.setRange(1, 32)
        self._min_slider.setValue(6)
        self._max_slider = QSlider(Qt.Orientation.Horizontal)
        self._max_slider.setRange(1, 32)
        self._max_slider.setValue(16)
        self._length_label = BodyLabel("6 — 16 characters")
        self._min_slider.valueChanged.connect(self._on_length_changed)
        self._max_slider.valueChanged.connect(self._on_length_changed)
        length_layout.addWidget(BodyLabel("Min:"))
        length_layout.addWidget(self._min_slider, 1)
        length_layout.addWidget(BodyLabel("Max:"))
        length_layout.addWidget(self._max_slider, 1)
        form.addLayout(length_layout)
        form.addWidget(self._length_label)

        form.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        # Footer: estimated candidate count
        footer = QWidget()
        footer.setStyleSheet("background: #17171C; border-top: 1px solid #2B2B33;")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(12, 8, 12, 8)
        self._candidate_lbl = BodyLabel("estimated ≈ — candidates")
        self._candidate_lbl.setStyleSheet("color: #7A7A84;")
        footer_layout.addWidget(self._candidate_lbl)
        footer_layout.addStretch(1)
        outer.addWidget(footer)

    def _add_date_row(self) -> None:
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)
        date_edit = QDateEdit(QDate.currentDate())
        date_edit.setCalendarPopup(True)
        date_edit.dateChanged.connect(self._on_hint_changed)
        label_combo = ComboBox()
        label_combo.addItems(["Date of Birth", "Anniversary", "Other"])
        self._date_rows.append((date_edit, label_combo))
        row_layout.addWidget(date_edit)
        row_layout.addWidget(label_combo)
        self._dates_container.addWidget(row_widget)

    def _on_hint_changed(self) -> None:
        count = self._estimate_candidates()
        if count >= 1_000_000:
            display = f"≈ {count / 1_000_000:.1f}M"
        elif count >= 1_000:
            display = f"≈ {count / 1_000:.0f}K"
        else:
            display = f"≈ {count}"
        self._candidate_lbl.setText(f"estimated {display} candidates")
        self.candidate_count_changed.emit(count)

    def _on_length_changed(self) -> None:
        mn = self._min_slider.value()
        mx = self._max_slider.value()
        if mn > mx:
            self._max_slider.setValue(mn)
            mx = mn
        self._length_label.setText(f"{mn} — {mx} characters")
        self._on_hint_changed()

    def _estimate_candidates(self) -> int:
        """Very rough candidate count estimate for display purposes."""
        stems = [s.strip() for s in self._stems_edit.text().split(",") if s.strip()]
        name_inputs: list[LineEdit] = (
            self._first_names
            + self._surnames
            + self._nicknames
            + self._pet_names
            + self._children_names
        )
        names = []
        for edit in name_inputs:
            names += [n.strip() for n in edit.text().split(",") if n.strip()]
        places = [e.text().strip() for e in self._place_edits if e.text().strip()]
        base_words = len(stems) + len(names) + len(places) + len(self._date_rows)
        if base_words == 0:
            base_words = 1
        suffixes = sum(1 for cb in self._suffix_checks.values() if cb.isChecked())
        multiplier = max(1, suffixes) * 4  # basic mutation factor
        return base_words * multiplier * 500

    def build_hints_kwargs(self) -> dict[str, object]:
        """Return kwargs suitable for constructing a Hints dataclass."""

        def _split(text: str) -> tuple[str, ...]:
            return tuple(s.strip() for s in text.split(",") if s.strip())

        dates: list[tuple[int, int, int]] = []
        for de, _ in self._date_rows:
            d = de.date()
            dates.append((d.day(), d.month(), d.year()))

        suffixes = tuple(tag for tag, cb in self._suffix_checks.items() if cb.isChecked())

        case_styles: list[str] = []
        if self._cb_upper.isChecked():
            case_styles.append("upper")
        if self._cb_lower.isChecked():
            case_styles.append("lower")
        if self._cb_digit.isChecked():
            case_styles.append("digit")
        if self._cb_symbol.isChecked():
            case_styles.append("symbol")

        return {
            "dates": tuple(dates),
            "first_names": _split(self._first_names[0].text()) if self._first_names else (),
            "surnames": _split(self._surnames[0].text()) if self._surnames else (),
            "nicknames": _split(self._nicknames[0].text()) if self._nicknames else (),
            "pet_names": _split(self._pet_names[0].text()) if self._pet_names else (),
            "places": tuple(e.text().strip() for e in self._place_edits if e.text().strip()),
            "stems": tuple(s.strip() for s in self._stems_edit.text().split(",") if s.strip()),
            "suffixes": suffixes,
            "case_styles": tuple(case_styles),
            "min_length": self._min_slider.value(),
            "max_length": self._max_slider.value(),
        }


class _StepStrategy(QWidget):
    """Step 3 — budget and GPU strategy."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(SubtitleLabel("Strategy"))

        # Budget slider
        budget_card = CardWidget()
        budget_inner = QVBoxLayout(budget_card)
        budget_inner.setContentsMargins(16, 14, 16, 14)
        budget_inner.setSpacing(10)
        budget_inner.addWidget(StrongBodyLabel("Time Budget"))

        slider_row = QHBoxLayout()
        self._budget_slider = QSlider(Qt.Orientation.Horizontal)
        self._budget_slider.setRange(0, len(_BUDGET_OPTIONS) - 1)
        self._budget_slider.setValue(2)  # 30 min default
        self._budget_label = BodyLabel(_BUDGET_OPTIONS[2][0])
        self._budget_label.setFixedWidth(60)
        self._budget_slider.valueChanged.connect(self._on_budget_changed)
        slider_row.addWidget(self._budget_slider, 1)
        slider_row.addWidget(self._budget_label)
        budget_inner.addLayout(slider_row)

        # Tick labels
        tick_row = QHBoxLayout()
        for label, _ in _BUDGET_OPTIONS:
            tick_lbl = CaptionLabel(label)
            tick_lbl.setStyleSheet("color: #7A7A84; font-size: 10px;")
            tick_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tick_row.addWidget(tick_lbl, 1)
        budget_inner.addLayout(tick_row)

        layout.addWidget(budget_card)

        # Low-power toggle
        power_card = CardWidget()
        power_inner = QHBoxLayout(power_card)
        power_inner.setContentsMargins(16, 12, 16, 12)
        power_inner.addWidget(BodyLabel("Low-power mode (−w 1, thermal limit 75°C)"), 1)
        self._low_power_cb = QCheckBox()
        power_inner.addWidget(self._low_power_cb)
        layout.addWidget(power_card)

        # Stage table
        layout.addWidget(StrongBodyLabel("Attack stages"))
        try:
            from PySide6.QtWidgets import QTableWidgetItem
            from qfluentwidgets import TableWidget

            self._table = TableWidget()
            self._table.setColumnCount(5)
            self._table.setHorizontalHeaderLabels(
                ["#", "Stage", "Engine", "Hit rate", "Budget share"]
            )
            self._table.setRowCount(len(_STAGE_TABLE))
            self._table.setEditTriggers(TableWidget.EditTrigger.NoEditTriggers)
            self._table.horizontalHeader().setStretchLastSection(True)
            for row, (no, name, engine, hit, share) in enumerate(_STAGE_TABLE):
                self._table.setItem(row, 0, QTableWidgetItem(str(no)))
                self._table.setItem(row, 1, QTableWidgetItem(name))
                self._table.setItem(row, 2, QTableWidgetItem(engine))
                self._table.setItem(row, 3, QTableWidgetItem(hit))
                self._table.setItem(row, 4, QTableWidgetItem(share))
        except Exception:
            from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

            self._table = QTableWidget()
            self._table.setColumnCount(5)
            self._table.setHorizontalHeaderLabels(
                ["#", "Stage", "Engine", "Hit rate", "Budget share"]
            )
            self._table.setRowCount(len(_STAGE_TABLE))
            self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            for row, (no, name, engine, hit, share) in enumerate(_STAGE_TABLE):
                self._table.setItem(row, 0, QTableWidgetItem(str(no)))
                self._table.setItem(row, 1, QTableWidgetItem(name))
                self._table.setItem(row, 2, QTableWidgetItem(engine))
                self._table.setItem(row, 3, QTableWidgetItem(hit))
                self._table.setItem(row, 4, QTableWidgetItem(share))
        layout.addWidget(self._table, 1)

    def _on_budget_changed(self, idx: int) -> None:
        self._budget_label.setText(_BUDGET_OPTIONS[idx][0])

    def get_budget_s(self) -> int:
        return _BUDGET_OPTIONS[self._budget_slider.value()][1]

    def is_low_power(self) -> bool:
        return self._low_power_cb.isChecked()


class _StepLaunch(QWidget):
    """Step 4 — summary and launch."""

    launch_requested: Signal = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(SubtitleLabel("Review & Launch"))

        self._summary_card = CardWidget()
        summary_inner = QVBoxLayout(self._summary_card)
        summary_inner.setContentsMargins(16, 14, 16, 14)
        summary_inner.setSpacing(8)
        self._summary_archive = BodyLabel("Archive: —")
        self._summary_format = BodyLabel("Format: —")
        self._summary_budget = BodyLabel("Budget: —")
        self._summary_hints = BodyLabel("Hints: —")
        self._summary_low_power = BodyLabel("Low-power: No")
        for lbl in (
            self._summary_archive,
            self._summary_format,
            self._summary_budget,
            self._summary_hints,
            self._summary_low_power,
        ):
            summary_inner.addWidget(lbl)
        layout.addWidget(self._summary_card)

        layout.addStretch(1)

        self._launch_btn = PrimaryPushButton("Start Recovery")
        self._launch_btn.setFixedHeight(44)
        self._launch_btn.clicked.connect(self.launch_requested)
        layout.addWidget(self._launch_btn)

    def populate(
        self,
        archive_path: str,
        archive_format: str,
        budget_label: str,
        hints_summary: str,
        low_power: bool,
    ) -> None:
        self._summary_archive.setText(f"Archive: {Path(archive_path).name}")
        self._summary_format.setText(f"Format: {archive_format}")
        self._summary_budget.setText(f"Budget: {budget_label}")
        self._summary_hints.setText(f"Hints: {hints_summary}")
        self._summary_low_power.setText(f"Low-power: {'Yes' if low_power else 'No'}")


# ---------------------------------------------------------------------------
# Main wizard page
# ---------------------------------------------------------------------------


class NewJobWizardPage(QWidget):
    """Multi-step new job wizard embedded in the main navigation."""

    session_started: Signal = Signal(str)  # session_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("newJobWizardPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        # Step indicator
        self._step_bar = _StepBar(steps=["Archive", "Hints", "Strategy", "Launch"])
        root.addWidget(self._step_bar)

        # Navigation buttons
        nav_row = QHBoxLayout()
        self._back_btn = PushButton("Back")
        self._next_btn = PrimaryPushButton("Next")
        self._skip_hints_btn = PushButton("Skip hints")
        self._skip_hints_btn.setVisible(False)
        self._back_btn.setEnabled(False)
        nav_row.addWidget(self._back_btn)
        nav_row.addWidget(self._skip_hints_btn)
        nav_row.addStretch(1)
        nav_row.addWidget(self._next_btn)

        # Stacked steps
        self._stack = QStackedWidget()
        self._step_archive = _StepArchive()
        self._step_hints = _StepHints()
        self._step_strategy = _StepStrategy()
        self._step_launch = _StepLaunch()
        for step in (
            self._step_archive,
            self._step_hints,
            self._step_strategy,
            self._step_launch,
        ):
            self._stack.addWidget(step)

        root.addWidget(self._stack, 1)
        root.addLayout(nav_row)

        self._back_btn.clicked.connect(self._go_back)
        self._next_btn.clicked.connect(self._go_next)
        self._skip_hints_btn.clicked.connect(self._skip_hints)
        self._step_launch.launch_requested.connect(self._on_launch)

        self._current_step = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_archive(self, path: Path) -> None:
        self._step_archive.set_archive(path)
        self._go_to_step(0)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _go_to_step(self, idx: int) -> None:
        self._current_step = idx
        self._stack.setCurrentIndex(idx)
        self._step_bar.set_active(idx)
        self._back_btn.setEnabled(idx > 0)
        is_last = idx == self._stack.count() - 1
        self._next_btn.setText("Next" if not is_last else "")
        self._next_btn.setVisible(not is_last)
        self._skip_hints_btn.setVisible(idx == 1)
        if idx == self._stack.count() - 1:
            self._populate_launch_summary()

    def _go_back(self) -> None:
        if self._current_step > 0:
            self._go_to_step(self._current_step - 1)

    def _go_next(self) -> None:
        if not self._validate_current_step():
            return
        next_step = self._current_step + 1
        if next_step < self._stack.count():
            self._go_to_step(next_step)

    def _skip_hints(self) -> None:
        self._go_to_step(2)  # jump to strategy

    def _validate_current_step(self) -> bool:
        if self._current_step == 0:
            info = self._step_archive.get_archive_info()
            if info is None:
                if InfoBar is not None:
                    InfoBar.warning(
                        title="No archive detected",
                        content="Please select and detect an archive first.",
                        parent=self,
                        position=InfoBarPosition.TOP,
                        duration=3000,
                    )
                return False
        return True

    def _populate_launch_summary(self) -> None:
        info = self._step_archive.get_archive_info()
        archive_path = str(info.path) if info else "—"
        archive_format = info.format if info else "—"
        budget_idx = self._step_strategy._budget_slider.value()
        budget_label = _BUDGET_OPTIONS[budget_idx][0]
        low_power = self._step_strategy.is_low_power()
        hints_kw = self._step_hints.build_hints_kwargs()
        names = hints_kw.get("first_names", ()) or hints_kw.get("stems", ())
        hints_summary = f"{len(names)} name(s), {len(hints_kw.get('dates', ()))} date(s)"
        self._step_launch.populate(
            archive_path, archive_format, budget_label, hints_summary, low_power
        )

    def _on_launch(self) -> None:
        info = self._step_archive.get_archive_info()
        if info is None:
            return
        hints_kw = self._step_hints.build_hints_kwargs()
        budget_s = self._step_strategy.get_budget_s()
        low_power = self._step_strategy.is_low_power()
        asyncio.ensure_future(self._launch_session(info, hints_kw, budget_s, low_power))

    async def _launch_session(
        self,
        archive_info: ArchiveInfo,
        hints_kw: dict[str, object],
        budget_s: int,
        low_power: bool,
    ) -> None:
        try:
            from uzpr.app import build_application  # lazy
            from uzpr.core.stages.protocol import Hints  # lazy

            hints = Hints(**hints_kw)  # type: ignore[arg-type]
            app = build_application()
            repo = app._repo  # type: ignore[attr-defined]
            session_id = await repo.create_session(archive_info, hints, float(budget_s), low_power)
            self.session_started.emit(session_id)
        except Exception as exc:
            if InfoBar is not None:
                InfoBar.error(
                    title="Launch failed",
                    content=str(exc),
                    parent=self,
                    position=InfoBarPosition.TOP,
                    duration=5000,
                )


# ---------------------------------------------------------------------------
# Step indicator bar
# ---------------------------------------------------------------------------


class _StepBar(QWidget):
    def __init__(self, steps: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._labels: list[QLabel] = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        for i, step in enumerate(steps):
            lbl = QLabel(f"{i + 1}. {step}")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedHeight(32)
            lbl.setStyleSheet(
                "QLabel { color: #7A7A84; background: #1F1F26;"
                " border-radius: 4px; padding: 4px 12px; font-size: 13px; }"
            )
            self._labels.append(lbl)
            layout.addWidget(lbl, 1)
            if i < len(steps) - 1:
                arrow = QLabel("›")
                arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
                arrow.setFixedWidth(20)
                arrow.setStyleSheet("color: #2B2B33; font-size: 16px;")
                layout.addWidget(arrow)
        self.set_active(0)

    def set_active(self, idx: int) -> None:
        for i, lbl in enumerate(self._labels):
            if i == idx:
                lbl.setStyleSheet(
                    "QLabel { color: #E8E8EE; background: #3B82F6;"
                    " border-radius: 4px; padding: 4px 12px; font-size: 13px; font-weight: bold; }"
                )
            elif i < idx:
                lbl.setStyleSheet(
                    "QLabel { color: #22C55E; background: #1F1F26;"
                    " border-radius: 4px; padding: 4px 12px; font-size: 13px; }"
                )
            else:
                lbl.setStyleSheet(
                    "QLabel { color: #7A7A84; background: #1F1F26;"
                    " border-radius: 4px; padding: 4px 12px; font-size: 13px; }"
                )
