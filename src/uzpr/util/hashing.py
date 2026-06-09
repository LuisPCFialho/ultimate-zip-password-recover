from __future__ import annotations

import hashlib
from pathlib import Path

try:
    import blake3 as _blake3  # type: ignore[import-untyped]

    _HAS_BLAKE3 = True
except ImportError:  # pragma: no cover
    _blake3 = None  # type: ignore[assignment]
    _HAS_BLAKE3 = False

_CHUNK = 65536  # 64 KB


def blake3_trunc16(s: str) -> bytes:
    """Hash *s* (UTF-8) with BLAKE3 (or SHA-256 fallback) and return 16 bytes."""
    raw = s.encode()
    if _HAS_BLAKE3:
        return _blake3.blake3(raw).digest()[:16]  # type: ignore[union-attr]
    return hashlib.sha256(raw).digest()[:16]


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 digest of a file, reading in 64 KB chunks."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
    return h.hexdigest()
