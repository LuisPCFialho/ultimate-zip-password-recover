from __future__ import annotations

"""First-run wizard with Simple Mode (3 steps) and Advanced Mode toggle.

Simple Mode is the friendly path: pick archive -> optional hints -> honest
estimate + start.  Advanced Mode embeds the existing 4-step
``NewJobWizardPage`` which exposes the full stage/budget/hint controls.

The preferred mode is persisted to ``~/.uzpr/settings.json`` so subsequent
launches remember the user's choice.  First launch defaults to Simple.
"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

try:
    from qfluentwidgets import (
        BodyLabel,
        CardWidget,
        ComboBox,
        InfoBar,
        InfoBarPosition,
        LineEdit,
        PrimaryPushButton,
        PushButton,
        Slider,
        StrongBodyLabel,
        SubtitleLabel,
        SwitchButton,
        TextEdit,
        TitleLabel,
    )

    _HAS_FLUENT = True
except ImportError:  # pragma: no cover - fallback for environments w/o qfluentwidgets
    from PySide6.QtWidgets import QComboBox as ComboBox  # type: ignore[assignment]
    from PySide6.QtWidgets import QFrame as CardWidget  # type: ignore[assignment]
    from PySide6.QtWidgets import QLabel as BodyLabel  # type: ignore[assignment]
    from PySide6.QtWidgets import QLabel as StrongBodyLabel  # type: ignore[assignment]
    from PySide6.QtWidgets import QLabel as SubtitleLabel  # type: ignore[assignment]
    from PySide6.QtWidgets import QLabel as TitleLabel  # type: ignore[assignment]
    from PySide6.QtWidgets import QLineEdit as LineEdit  # type: ignore[assignment]
    from PySide6.QtWidgets import QPushButton as PrimaryPushButton  # type: ignore[assignment]
    from PySide6.QtWidgets import QPushButton as PushButton  # type: ignore[assignment]
    from PySide6.QtWidgets import QSlider as Slider  # type: ignore[assignment]
    from PySide6.QtWidgets import QCheckBox as SwitchButton  # type: ignore[assignment]
    from PySide6.QtWidgets import QTextEdit as TextEdit  # type: ignore[assignment]

    InfoBar = None  # type: ignore[assignment,misc]
    InfoBarPosition = None  # type: ignore[assignment,misc]
    _HAS_FLUENT = False

if TYPE_CHECKING:
    from uzpr.app import AppState
    from uzpr.archive.detect import ArchiveInfo


# ---------------------------------------------------------------------------
# Settings persistence
# ---------------------------------------------------------------------------

_SETTINGS_DIR = Path.home() / ".uzpr"
_SETTINGS_FILE = _SETTINGS_DIR / "settings.json"

MODE_SIMPLE = "simple"
MODE_ADVANCED = "advanced"


def load_preferred_mode() -> str:
    """Return the persisted preferred mode, defaulting to Simple on first launch."""
    try:
        data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        mode = data.get("preferred_mode")
        if mode in (MODE_SIMPLE, MODE_ADVANCED):
            return mode
    except (OSError, ValueError):
        pass
    return MODE_SIMPLE


def save_preferred_mode(mode: str) -> None:
    """Persist the preferred mode to ``~/.uzpr/settings.json``."""
    if mode not in (MODE_SIMPLE, MODE_ADVANCED):
        return
    try:
        _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        existing: dict[str, object] = {}
        if _SETTINGS_FILE.exists():
            try:
                existing = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
            except ValueError:
                existing = {}
        existing["preferred_mode"] = mode
        _SETTINGS_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DATE_RE = re.compile(r"^\s*(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\s*$")


def _parse_dates(text: str) -> tuple[tuple[int, int, int], ...]:
    """Parse comma- or newline-separated DD/MM/YYYY entries."""
    parts = re.split(r"[,\n]+", text)
    out: list[tuple[int, int, int]] = []
    for part in parts:
        m = _DATE_RE.match(part)
        if not m:
            continue
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000 if y < 50 else 1900
        try:
            datetime(y, mo, d)
        except ValueError:
            continue
        out.append((d, mo, y))
    return tuple(out)


def _split_csv(text: str) -> tuple[str, ...]:
    return tuple(s.strip() for s in re.split(r"[,\n]+", text) if s.strip())


def _has_stored_entry(info: ArchiveInfo) -> bool:
    """Return True if any ZIP entry uses STORED compression (method 0)."""
    for entry in info.entries:
        method = getattr(entry, "method", None)
        if method == 0:
            return True
    return False


# ---------------------------------------------------------------------------
# Simple Mode steps
# ---------------------------------------------------------------------------


class _SimpleStepArchive(QWidget):
    """Step 1 — pick the archive and show a single-line verdict."""

    archive_ready: Signal = Signal(object)  # ArchiveInfo

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(TitleLabel("Pick the archive"))
        layout.addWidget(
            BodyLabel(
                "Drop a .zip or .rar file here, or use Browse. We will detect"
                " the format automatically."
            )
        )

        # Drop zone
        self._drop = QLabel("Drop archive here")
        self._drop.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drop.setMinimumHeight(160)
        self._drop.setStyleSheet(
            "QLabel { border: 2px dashed #555; border-radius: 8px;"
            " color: #888; font-size: 16px; padding: 24px; }"
        )
        self._drop.setAcceptDrops(False)
        self.setAcceptDrops(True)
        layout.addWidget(self._drop)

        row = QHBoxLayout()
        self._browse = PrimaryPushButton("Browse...")
        self._browse.clicked.connect(self._on_browse)
        row.addWidget(self._browse)
        row.addStretch(1)
        layout.addLayout(row)

        self._verdict = BodyLabel("")
        self._verdict.setWordWrap(True)
        layout.addWidget(self._verdict)

        layout.addStretch(1)

        self._archive_info: ArchiveInfo | None = None

    # Drag & drop
    def dragEnterEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        urls = event.mimeData().urls()
        if not urls:
            return
        path = Path(urls[0].toLocalFile())
        self._set_archive(path)

    def _on_browse(self) -> None:
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Select archive", "", "Archive files (*.zip *.rar);;All files (*)"
        )
        if path_str:
            self._set_archive(Path(path_str))

    def _set_archive(self, path: Path) -> None:
        if path.suffix.lower() not in (".zip", ".rar"):
            self._verdict.setText("Unsupported file type. Please choose a .zip or .rar file.")
            return
        if not path.exists():
            self._verdict.setText("File not found.")
            return
        try:
            from uzpr.archive.detect import detect_archive

            info = detect_archive(path)
        except Exception as exc:
            self._verdict.setText(f"Could not read archive: {exc}")
            return

        self._archive_info = info
        self._drop.setText(path.name)
        verdict = self._build_verdict(info)
        self._verdict.setText(verdict)
        self.archive_ready.emit(info)

    @staticmethod
    def _build_verdict(info: ArchiveInfo) -> str:
        fmt = info.format
        if fmt == "zip-classic":
            return "ZipCrypto archive - fast recovery likely."
        if fmt == "zip-aes":
            strength = info.aes_strength or 256
            return (
                f"AES-{strength} archive - slower; provide hints if possible."
            )
        if fmt == "rar3-hp":
            return "RAR3 header-encrypted archive - slow; hints recommended."
        if fmt == "rar5":
            return "RAR5 archive - very slow; strong hints recommended."
        if fmt == "pkware-strong":
            return "PKWARE Strong Encryption - not recoverable by brute force."
        if fmt == "plain":
            return "Archive is not encrypted - no recovery needed."
        return f"Detected format: {fmt}."

    def get_archive_info(self) -> ArchiveInfo | None:
        return self._archive_info


class _SimpleStepHints(QWidget):
    """Step 2 — friendly optional hints."""

    skip_requested: Signal = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(TitleLabel("Do you remember anything?"))
        layout.addWidget(
            BodyLabel(
                "All fields are optional. Anything you provide helps us find"
                " the password faster."
            )
        )

        layout.addWidget(StrongBodyLabel("Names that might be in it"))
        self._names = LineEdit()
        self._names.setPlaceholderText("e.g. Anna, Bruno, Catarina")
        layout.addWidget(self._names)

        layout.addWidget(StrongBodyLabel("Important dates (DD/MM/YYYY)"))
        self._dates = TextEdit()
        self._dates.setPlaceholderText("e.g. 14/02/1990, 25/12/2010")
        self._dates.setFixedHeight(70)
        layout.addWidget(self._dates)

        layout.addWidget(StrongBodyLabel("Words or topics"))
        self._stems = LineEdit()
        self._stems.setPlaceholderText("e.g. summer, holiday, work")
        layout.addWidget(self._stems)

        layout.addWidget(StrongBodyLabel("Roughly how long?"))
        len_row = QHBoxLayout()
        self._len_slider = Slider(Qt.Orientation.Horizontal)
        self._len_slider.setRange(4, 20)
        self._len_slider.setValue(8)
        self._len_label = BodyLabel("around 8 characters")
        self._len_slider.valueChanged.connect(
            lambda v: self._len_label.setText(f"around {v} characters")
        )
        len_row.addWidget(self._len_slider, 1)
        len_row.addWidget(self._len_label)
        layout.addLayout(len_row)

        layout.addWidget(StrongBodyLabel("Language"))
        self._locale = ComboBox()
        self._locale.addItems(["Portugues", "English", "Other"])
        layout.addWidget(self._locale)

        layout.addStretch(1)

        skip = PushButton("Skip - I don't remember")
        skip.clicked.connect(self.skip_requested)
        layout.addWidget(skip)

    def build_hints_dict(self) -> dict[str, object]:
        center = self._len_slider.value()
        min_len = max(1, center - 2)
        max_len = min(32, center + 2)

        locale_map = {"Portugues": "pt-PT", "English": "en-GB", "Other": "en-GB"}
        locale = locale_map.get(self._locale.currentText(), "en-GB")

        return {
            "first_names": list(_split_csv(self._names.text())),
            "dates": [list(d) for d in _parse_dates(self._dates.toPlainText())],
            "stems": list(_split_csv(self._stems.text())),
            "min_length": min_len,
            "max_length": max_len,
            "locale": locale,
        }


class _SimpleStepEstimate(QWidget):
    """Step 3 — honest estimate + Start button."""

    start_requested: Signal = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(TitleLabel("Honest estimate"))

        self._estimate_card = CardWidget()
        inner = QVBoxLayout(self._estimate_card)
        inner.setContentsMargins(20, 16, 20, 16)
        self._estimate_label = BodyLabel("")
        self._estimate_label.setWordWrap(True)
        inner.addWidget(self._estimate_label)
        layout.addWidget(self._estimate_card)

        layout.addStretch(1)

        self._start_btn = PrimaryPushButton("Start Recovery")
        self._start_btn.setFixedHeight(48)
        self._start_btn.clicked.connect(self.start_requested)
        layout.addWidget(self._start_btn)

    def populate(self, info: ArchiveInfo | None, hints: dict[str, object]) -> None:
        self._estimate_label.setText(self._build_estimate(info, hints))

    @staticmethod
    def _build_estimate(info: ArchiveInfo | None, hints: dict[str, object]) -> str:
        if info is None:
            return "Select an archive first."
        fmt = info.format
        has_hints = bool(
            hints.get("first_names") or hints.get("dates") or hints.get("stems")
        )

        if fmt == "zip-classic":
            if _has_stored_entry(info):
                return (
                    "ZipCrypto with a STORED (uncompressed) entry detected."
                    " Likely seconds to minutes. Starting recovery."
                )
            return (
                "ZipCrypto archive. Could take hours to days without a known"
                " plaintext. Hints help a lot."
            )
        if fmt == "zip-aes":
            if has_hints:
                return (
                    "AES-256 archive with hints. Hours to a day for short"
                    " passwords; longer otherwise."
                )
            return (
                "AES-256 archive with no hints. Honestly: if the password is"
                " random and 10+ characters, recovery is very unlikely."
                " We'll try our best. Free app, no charge."
            )
        if fmt == "rar3-hp":
            return "RAR3 header-encrypted. Slow but feasible if password is short or hinted."
        if fmt == "rar5":
            return (
                "RAR5 archive. Very slow GPU attack. Without strong hints,"
                " recovery is unlikely. We'll try our best."
            )
        if fmt == "pkware-strong":
            return (
                "PKWARE Strong Encryption is not recoverable by brute force."
                " Only a known password will work."
            )
        if fmt == "plain":
            return "Archive is not encrypted - no password needed."
        return "Unknown format. We'll attempt detection during the run."


# ---------------------------------------------------------------------------
# Progress screen
# ---------------------------------------------------------------------------


class _ProgressScreen(QWidget):
    """Minimal progress view: current stage, elapsed time, cancel."""

    cancel_requested: Signal = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(TitleLabel("Recovering..."))
        self._stage_label = BodyLabel("Starting...")
        layout.addWidget(self._stage_label)
        self._elapsed_label = BodyLabel("Elapsed: 0s")
        layout.addWidget(self._elapsed_label)

        self._result_card = CardWidget()
        result_inner = QVBoxLayout(self._result_card)
        result_inner.setContentsMargins(20, 16, 20, 16)
        self._result_label = StrongBodyLabel("")
        self._result_label.setWordWrap(True)
        result_inner.addWidget(self._result_label)
        self._password_edit = LineEdit()
        self._password_edit.setReadOnly(True)
        result_inner.addWidget(self._password_edit)
        self._result_card.setVisible(False)
        layout.addWidget(self._result_card)

        layout.addStretch(1)

        self._cancel = PushButton("Cancel")
        self._cancel.clicked.connect(self.cancel_requested)
        layout.addWidget(self._cancel)

    def set_stage(self, name: str) -> None:
        self._stage_label.setText(f"Current stage: {name}")

    def set_elapsed(self, seconds: int) -> None:
        self._elapsed_label.setText(f"Elapsed: {seconds}s")

    def show_found(self, password: str) -> None:
        self._result_label.setText("Password found:")
        self._password_edit.setText(password)
        self._result_card.setVisible(True)
        self._cancel.setText("Close")


# ---------------------------------------------------------------------------
# Simple Mode container
# ---------------------------------------------------------------------------


class SimpleModeWidget(QWidget):
    """Three-step Simple Mode wizard."""

    session_started: Signal = Signal(str)

    def __init__(self, app_state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._app = app_state

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        self._stack = QStackedWidget()
        self._step_archive = _SimpleStepArchive()
        self._step_hints = _SimpleStepHints()
        self._step_estimate = _SimpleStepEstimate()
        self._progress = _ProgressScreen()
        for w in (self._step_archive, self._step_hints, self._step_estimate, self._progress):
            self._stack.addWidget(w)
        layout.addWidget(self._stack, 1)

        nav_row = QHBoxLayout()
        self._back_btn = PushButton("Back")
        self._next_btn = PrimaryPushButton("Next")
        self._back_btn.setEnabled(False)
        self._back_btn.clicked.connect(self._go_back)
        self._next_btn.clicked.connect(self._go_next)
        nav_row.addWidget(self._back_btn)
        nav_row.addStretch(1)
        nav_row.addWidget(self._next_btn)
        layout.addLayout(nav_row)

        self._step_archive.archive_ready.connect(self._on_archive_ready)
        self._step_hints.skip_requested.connect(self._on_skip_hints)
        self._step_estimate.start_requested.connect(self._on_start)

        self._idx = 0

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _set_step(self, idx: int) -> None:
        self._idx = idx
        self._stack.setCurrentIndex(idx)
        self._back_btn.setEnabled(0 < idx < 3)
        # Hide nav row on progress screen and on estimate (uses Start button)
        on_nav_step = idx in (0, 1)
        self._next_btn.setVisible(on_nav_step)
        if idx == 2:
            hints = self._step_hints.build_hints_dict()
            self._step_estimate.populate(self._step_archive.get_archive_info(), hints)

    def _go_back(self) -> None:
        if self._idx > 0 and self._idx < 3:
            self._set_step(self._idx - 1)

    def _go_next(self) -> None:
        if self._idx == 0:
            if self._step_archive.get_archive_info() is None:
                self._warn("Please select an archive first.")
                return
        if self._idx < 2:
            self._set_step(self._idx + 1)

    def _on_archive_ready(self, _info: object) -> None:
        # Enable next, but don't auto-advance — user clicks Next.
        pass

    def _on_skip_hints(self) -> None:
        self._set_step(2)

    # ------------------------------------------------------------------
    # Launch
    # ------------------------------------------------------------------

    def _on_start(self) -> None:
        info = self._step_archive.get_archive_info()
        if info is None:
            self._warn("Please select an archive first.")
            return
        hints_raw = self._step_hints.build_hints_dict()
        self._set_step(3)
        self._progress.set_stage("Initializing")
        asyncio.ensure_future(self._launch(info, hints_raw))

    async def _launch(self, info: ArchiveInfo, hints_raw: dict[str, object]) -> None:
        try:
            from uzpr.core.hints import normalize_hints

            hints = normalize_hints(hints_raw)
            session_id = await self._app.repo.create_session(
                info, hints, 1800.0, False
            )
            self.session_started.emit(session_id)
        except Exception as exc:
            self._warn(f"Launch failed: {exc}")
            self._set_step(2)

    def _warn(self, message: str) -> None:
        if InfoBar is not None:
            InfoBar.warning(
                title="Hold on",
                content=message,
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3500,
            )


# ---------------------------------------------------------------------------
# Wizard window (Simple/Advanced shell)
# ---------------------------------------------------------------------------


class WizardWindow(QWidget):
    """Top-level wizard widget with a Simple/Advanced toggle.

    Advanced Mode embeds the existing :class:`NewJobWizardPage`.  Simple Mode
    is the 3-step friendly flow above.
    """

    session_started: Signal = Signal(str)

    def __init__(self, app_state: AppState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("wizardWindow")
        self._app = app_state

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top bar with mode toggle
        top = QWidget()
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(24, 12, 24, 8)
        top_layout.addWidget(SubtitleLabel("New Recovery Job"))
        top_layout.addStretch(1)
        top_layout.addWidget(BodyLabel("Mode:"))
        self._mode_label = StrongBodyLabel("Simple")
        top_layout.addWidget(self._mode_label)
        self._mode_toggle = SwitchButton()
        if _HAS_FLUENT:
            try:
                self._mode_toggle.setOnText("Advanced")
                self._mode_toggle.setOffText("Simple")
            except AttributeError:
                pass
        self._mode_toggle.setChecked(load_preferred_mode() == MODE_ADVANCED)
        top_layout.addWidget(self._mode_toggle)
        layout.addWidget(top)

        # Stacked Simple / Advanced
        self._content = QStackedWidget()
        self._simple = SimpleModeWidget(app_state)
        self._simple.session_started.connect(self.session_started)
        self._content.addWidget(self._simple)

        # Advanced page is constructed lazily on first switch.  Construction
        # of the full NewJobWizardPage is expensive (builds a 13-row table,
        # multiple sliders, etc.) so we don't pay that cost unless the user
        # actually flips the toggle.
        self._advanced: QWidget | None = None
        self._advanced_placeholder = QWidget()
        _ph_layout = QVBoxLayout(self._advanced_placeholder)
        _ph_layout.addWidget(BodyLabel("Loading Advanced Mode..."))
        _ph_layout.addStretch(1)
        self._content.addWidget(self._advanced_placeholder)

        layout.addWidget(self._content, 1)

        # Initial state
        self._apply_mode(load_preferred_mode())
        self._mode_toggle.checkedChanged.connect(self._on_toggle) if _HAS_FLUENT else self._mode_toggle.toggled.connect(  # type: ignore[attr-defined]
            self._on_toggle
        )

    def _on_toggle(self, checked: bool) -> None:
        mode = MODE_ADVANCED if checked else MODE_SIMPLE
        self._apply_mode(mode)
        save_preferred_mode(mode)

    def _ensure_advanced(self) -> QWidget:
        """Build the Advanced page on first access; return it."""
        if self._advanced is not None:
            return self._advanced
        try:
            from uzpr.ui.pages.new_job_wizard import NewJobWizardPage

            adv: QWidget = NewJobWizardPage(self._app)
            sig = getattr(adv, "session_started", None)
            if sig is not None:
                sig.connect(self.session_started)
        except Exception:
            adv = QWidget()
            layout = QVBoxLayout(adv)
            layout.addWidget(
                BodyLabel(
                    "Advanced Mode is not available in this build."
                    " Switch back to Simple Mode."
                )
            )
            layout.addStretch(1)
        self._advanced = adv
        self._content.addWidget(adv)
        return adv

    def _apply_mode(self, mode: str) -> None:
        if mode == MODE_ADVANCED:
            adv = self._ensure_advanced()
            self._content.setCurrentWidget(adv)
            self._mode_label.setText("Advanced")
        else:
            self._content.setCurrentWidget(self._simple)
            self._mode_label.setText("Simple")

    # Allow MainWindow to forward archive selection from the Home page.
    def set_archive(self, path: Path) -> None:
        if self._advanced is not None:
            adv_set = getattr(self._advanced, "set_archive", None)
            if callable(adv_set):
                try:
                    adv_set(path)
                except Exception:
                    pass
        # Also pass to Simple mode's archive step
        self._simple._step_archive._set_archive(path)  # noqa: SLF001
