"""Download an installer from a GitHub Release asset URL."""

from __future__ import annotations

import logging
import urllib.request
from collections.abc import Callable
from pathlib import Path

from uzpr.updater.check import UpdateInfo

log = logging.getLogger(__name__)

_CHUNK = 64 * 1024
ProgressCb = Callable[[int, int], None]


def download_installer(
    info: UpdateInfo,
    dest_dir: Path,
    *,
    progress: ProgressCb | None = None,
    timeout: float = 30.0,
) -> Path:
    """Download ``info.installer_url`` to ``dest_dir`` and return the file path.

    Does NOT execute the installer. The caller is responsible for launching.
    """
    if not info.installer_url:
        raise ValueError("UpdateInfo has no installer_url")

    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = info.installer_url.rsplit("/", 1)[-1] or f"UZPR-Setup-{info.version}.exe"
    out = dest_dir / filename

    req = urllib.request.Request(info.installer_url, headers={"User-Agent": "uzpr-updater"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        total = int(resp.headers.get("Content-Length", "0") or 0)
        written = 0
        with out.open("wb") as f:
            while True:
                chunk = resp.read(_CHUNK)
                if not chunk:
                    break
                f.write(chunk)
                written += len(chunk)
                if progress is not None:
                    progress(written, total)

    if out.stat().st_size == 0:
        raise OSError(f"downloaded installer is empty: {out}")

    log.info("installer_downloaded: %s (%d bytes)", out, out.stat().st_size)
    return out
