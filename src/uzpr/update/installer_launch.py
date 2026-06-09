from __future__ import annotations

import sys
from pathlib import Path

from uzpr.util.logging import get_logger

log = get_logger(__name__)

# Windows PROCESS_CREATION_FLAGS
_DETACHED_PROCESS = 0x00000008


def launch_installer(installer_path: Path) -> None:
    """Spawn the Inno Setup installer silently then exit this process.

    The installer runs detached so that UZPR can exit before the installer
    replaces its own files.  On non-Windows platforms this is a no-op that
    logs a warning.
    """
    if sys.platform != "win32":
        log.warning(
            "auto_update_not_supported",
            platform=sys.platform,
            message="auto-update not supported on this platform",
        )
        return

    import subprocess

    subprocess.Popen(
        [str(installer_path), "/VERYSILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"],
        creationflags=_DETACHED_PROCESS,
    )
    sys.exit(0)
