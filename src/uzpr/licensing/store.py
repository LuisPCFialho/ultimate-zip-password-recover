from __future__ import annotations

from pathlib import Path

import platformdirs

from uzpr.persistence.encryption import dpapi_decrypt, dpapi_encrypt
from uzpr.util.logging import get_logger

log = get_logger(__name__)

_DEFAULT_FILENAME = "license.bin"


def _default_store_path() -> Path:
    return (
        Path(platformdirs.user_data_dir("UltimateZipPasswordRecover", False))
        / _DEFAULT_FILENAME
    )


class LicenseStore:
    """Persist the license token on disk using DPAPI encryption."""

    def __init__(self, store_path: Path | None = None) -> None:
        self._path: Path = store_path if store_path is not None else _default_store_path()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self) -> bytes | None:
        """Return the raw license token bytes, or *None* if not present / unreadable."""
        if not self._path.exists():
            return None
        try:
            encrypted = self._path.read_bytes()
            return dpapi_decrypt(encrypted)
        except Exception as exc:
            log.warning("license_store_read_failed", path=str(self._path), exc=str(exc))
            return None

    def set(self, token: bytes) -> None:
        """Encrypt and persist *token* to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        encrypted = dpapi_encrypt(token)
        self._path.write_bytes(encrypted)
        log.debug("license_store_written", path=str(self._path))

    def clear(self) -> None:
        """Remove the stored license file if it exists."""
        if self._path.exists():
            self._path.unlink()
            log.info("license_store_cleared", path=str(self._path))
