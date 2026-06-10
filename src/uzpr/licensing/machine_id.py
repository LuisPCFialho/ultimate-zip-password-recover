"""Stable machine identifier for license binding.

Uses Windows MachineGuid registry value combined with the first MAC address
from ``uuid.getnode()``. Falls back to MAC alone if the registry read fails.
"""

from __future__ import annotations

import hashlib
import sys
import uuid


def _read_windows_machine_guid() -> str:
    if sys.platform != "win32":
        return ""
    try:
        import winreg  # type: ignore[import-not-found]

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value)
    except Exception:
        return ""


def get_machine_id() -> str:
    """Return a stable hex string identifying the current machine."""
    guid = _read_windows_machine_guid()
    mac = format(uuid.getnode(), "012x")
    raw = f"{guid}|{mac}".encode()
    return hashlib.sha256(raw).hexdigest()
