from __future__ import annotations

"""Thread-safe (single-threaded GUI) JSON settings store backed by ~/.uzpr/settings.json."""

import json
from pathlib import Path
from typing import Any


class SettingsStore:
    """Read/write key-value settings persisted to a JSON file.

    Lazy-loads on first access; only writes when :meth:`save` is called.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path: Path = path or (Path.home() / ".uzpr" / "settings.json")
        self._data: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._data is not None:
            return
        try:
            self._data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self._data = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        self._ensure_loaded()
        assert self._data is not None
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._ensure_loaded()
        assert self._data is not None
        self._data[key] = value

    def save(self) -> None:
        self._ensure_loaded()
        assert self._data is not None
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
