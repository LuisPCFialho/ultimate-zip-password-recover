from __future__ import annotations

import os
import sys
from pathlib import Path

_APP_NAME = "UltimateZipPasswordRecover"


def localappdata_dir() -> Path:
    """Return %LOCALAPPDATA%/UltimateZipPasswordRecover, creating it if absent."""
    base = os.environ.get("LOCALAPPDATA")
    if base:
        root = Path(base) / _APP_NAME
    else:
        # Fallback for environments where %LOCALAPPDATA% is unset.
        import platformdirs  # type: ignore[import-untyped]

        root = Path(platformdirs.user_data_dir(_APP_NAME, False))
    root.mkdir(parents=True, exist_ok=True)
    return root


def install_dir() -> Path:
    """Return the PyInstaller bundle dir when frozen, else the project root."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    # Two parents above this file: src/uzpr/util/paths.py → project root
    return Path(__file__).resolve().parent.parent.parent.parent


def tools_dir() -> Path:
    """Return the tools/ directory inside the install dir."""
    return install_dir() / "tools"


def sessions_dir() -> Path:
    """Return the sessions directory inside localappdata_dir."""
    return localappdata_dir() / "sessions"


def session_work_dir(session_id: str) -> Path:
    """Return (and create) a per-session working directory."""
    d = sessions_dir() / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    """Return the path to the SQLite database file."""
    return localappdata_dir() / "uzpr.db"


def logs_dir() -> Path:
    """Return the logs directory inside localappdata_dir, creating it if absent."""
    d = localappdata_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d
