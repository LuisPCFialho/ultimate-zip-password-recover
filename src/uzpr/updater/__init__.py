"""Stdlib-based GitHub Releases update checker with 24h throttle.

Separate from :mod:`uzpr.update` (which uses httpx async). This module is
synchronous, stdlib-only for the network call, and persists last-check state
in ``~/.uzpr/settings.json``.
"""

from __future__ import annotations

from uzpr.updater.check import (
    UpdateInfo,
    check_for_update,
    current_version,
)
from uzpr.updater.download import download_installer

__all__ = [
    "UpdateInfo",
    "check_for_update",
    "current_version",
    "download_installer",
]
