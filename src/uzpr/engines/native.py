from __future__ import annotations

from pathlib import Path

import anyio

from uzpr.util.logging import get_logger

log = get_logger(__name__)


class NativeVerifier:
    """Verifies passwords in-process using pyzipper / rarfile, no subprocess."""

    def __init__(self, archive: Path, fmt: str) -> None:
        self._archive = archive
        self._fmt = fmt

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def verify(self, candidate: str) -> bool:
        """Return True if *candidate* unlocks the archive."""
        return await anyio.to_thread.run_sync(
            lambda: self._verify_sync(candidate),
            limiter=None,
        )

    async def verify_batch(self, candidates: list[str]) -> str | None:
        """Return the first candidate that opens the archive, or None."""
        for candidate in candidates:
            ok = await anyio.to_thread.run_sync(
                lambda c=candidate: self._verify_sync(c),
                limiter=None,
            )
            if ok:
                return candidate
        return None

    # ------------------------------------------------------------------
    # Sync helpers (run in a thread)
    # ------------------------------------------------------------------

    def _verify_sync(self, candidate: str) -> bool:
        """Try to decrypt the first entry; return True on success."""
        fmt = self._fmt
        if fmt in ("zip-classic", "zip-aes"):
            return self._verify_zip(candidate)
        if fmt in ("rar3-hp", "rar5"):
            return self._verify_rar(candidate)
        log.warning("native_verifier_unknown_fmt", fmt=fmt)
        return False

    def _verify_zip(self, candidate: str) -> bool:
        try:
            import pyzipper  # type: ignore[import-untyped]

            entry = _pick_entry(self._archive)
            with pyzipper.AESZipFile(self._archive) as zf:
                zf.setpassword(candidate.encode("utf-8", errors="replace"))
                zf.read(entry)
            return True
        except Exception:
            return False

    def _verify_rar(self, candidate: str) -> bool:
        try:
            import rarfile  # type: ignore[import-untyped]

            with rarfile.RarFile(self._archive) as rf:
                rf.setpassword(candidate)
                info_list = rf.infolist()
                if not info_list:
                    return False
                rf.read(info_list[0])
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Private entry-selection helper
# ---------------------------------------------------------------------------


def _pick_entry(archive: Path) -> str:
    """Return the name of the smallest encrypted entry in a ZIP archive.

    Falls back to the first entry if no encrypted entries are found.
    """
    import pyzipper  # type: ignore[import-untyped]

    best_name: str | None = None
    best_size: int = -1

    with pyzipper.AESZipFile(archive) as zf:
        for info in zf.infolist():
            # flag_bits bit 0 == encrypted
            is_encrypted = bool(info.flag_bits & 0x1)
            if not is_encrypted:
                continue
            size = info.compress_size
            if best_name is None or size < best_size:
                best_name = info.filename
                best_size = size

    if best_name is not None:
        return best_name

    # Fallback: return first entry regardless of encryption flag
    with pyzipper.AESZipFile(archive) as zf:
        infos = zf.infolist()
        if infos:
            return infos[0].filename

    raise ValueError(f"ZIP archive has no entries: {archive}")
