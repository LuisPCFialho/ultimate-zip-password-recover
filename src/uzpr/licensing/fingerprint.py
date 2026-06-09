from __future__ import annotations

import base64
import hashlib
import hmac
import platform
import subprocess
import sys
from typing import NamedTuple

from uzpr.util.logging import get_logger

log = get_logger(__name__)

_HMAC_KEY = b"uzpr-v1"


def _collect_macs() -> str:
    """Return a sorted, ';'-joined string of non-null MAC addresses."""
    try:
        import psutil

        macs: list[str] = sorted(
            {
                addr.address
                for iface_addrs in psutil.net_if_addrs().values()
                for addr in iface_addrs
                if addr.family.name == "AF_LINK"
                and addr.address not in ("", "00:00:00:00:00:00")
            }
        )
        return ";".join(macs)
    except Exception as exc:
        log.warning("fingerprint_mac_collection_failed", exc=str(exc))
        return ""


def _collect_cpu() -> str:
    """Return CPU brand string."""
    try:
        import cpuinfo  # type: ignore[import-untyped]

        return str(cpuinfo.get_cpu_info().get("brand_raw", platform.processor()))
    except Exception:
        return platform.processor()


def _collect_board_serial() -> str:
    """Return motherboard serial on Windows; empty string on other platforms."""
    if sys.platform != "win32":
        return ""
    try:
        result = subprocess.run(
            ["wmic", "path", "Win32_BaseBoard", "get", "SerialNumber", "/value"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                if key.strip().lower() == "serialnumber":
                    return value.strip()
    except Exception as exc:
        log.warning("fingerprint_board_serial_failed", exc=str(exc))
    return ""


def machine_fingerprint() -> str:
    """Return a stable 16-char base32 machine fingerprint.

    Derived from MAC addresses, CPU brand, and motherboard serial number
    (Windows only) via HMAC-SHA256 with key ``b'uzpr-v1'``.
    """
    macs = _collect_macs()
    cpu = _collect_cpu()
    serial = _collect_board_serial()

    raw = ";".join([macs, cpu, serial]).encode()
    digest = hmac.new(_HMAC_KEY, raw, hashlib.sha256).digest()
    return base64.b32encode(digest[:10]).decode().rstrip("=")[:16]
