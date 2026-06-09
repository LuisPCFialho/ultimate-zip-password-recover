from __future__ import annotations

"""Application theme bootstrap and colour tokens."""

import pathlib

from PySide6.QtGui import QFontDatabase
from qfluentwidgets import Theme, setTheme, setThemeColor

# Architecture spec: accent #3B82F6, dark surfaces #0F0F12/#17171C/#1F1F26/#2B2B33
ACCENT_COLOR = "#3B82F6"

DARK_SURFACE_0 = "#0F0F12"
DARK_SURFACE_1 = "#17171C"
DARK_SURFACE_2 = "#1F1F26"
DARK_SURFACE_3 = "#2B2B33"

TEXT_PRIMARY = "#E8E8EE"
TEXT_SECONDARY = "#B4B4BC"
TEXT_TERTIARY = "#7A7A84"


def apply_theme(dark: bool | None = None) -> None:
    """Apply Fluent theme + accent colour.

    Args:
        dark: True → DARK, False → LIGHT, None → AUTO (default per architecture spec).
    """
    if dark is None:
        setTheme(Theme.AUTO)
    elif dark:
        setTheme(Theme.DARK)
    else:
        setTheme(Theme.LIGHT)

    setThemeColor(ACCENT_COLOR)


def load_fonts() -> None:
    """Register Inter and JetBrains Mono from assets/fonts/ if present."""
    fonts_dir = pathlib.Path(__file__).parent / "assets" / "fonts"
    if fonts_dir.exists():
        for font_file in fonts_dir.glob("*.ttf"):
            QFontDatabase.addApplicationFont(str(font_file))
