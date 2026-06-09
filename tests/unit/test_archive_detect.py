from __future__ import annotations

import struct
from pathlib import Path

from uzpr.archive.detect import detect_archive


def _make_plaintext_zip(path: Path) -> None:
    """Write a minimal valid plaintext ZIP local header (not encrypted)."""
    # PK\x03\x04, version=20, gp_flag=0 (not encrypted), method=8 (deflate)
    fname = b"test.txt"
    hdr = struct.pack("<4sHHHHHIIIHH", b"PK\x03\x04", 20, 0, 8, 0, 0, 0, 0, 0, len(fname), 0)
    with open(path, "wb") as f:
        f.write(hdr + fname)


def _make_encrypted_zip(path: Path) -> None:
    """Write a minimal encrypted ZIP local header (GP flag bit 0 set)."""
    fname = b"test.txt"
    hdr = struct.pack("<4sHHHHHIIIHH", b"PK\x03\x04", 20, 1, 8, 0, 0, 0, 0, 0, len(fname), 0)
    with open(path, "wb") as f:
        f.write(hdr + fname)


def test_plaintext_zip_detected(tmp_path: Path) -> None:
    p = tmp_path / "test.zip"
    _make_plaintext_zip(p)
    info = detect_archive(p)
    assert info.format == "plain"


def test_encrypted_zip_detected(tmp_path: Path) -> None:
    p = tmp_path / "test.zip"
    _make_encrypted_zip(p)
    info = detect_archive(p)
    assert info.format == "zip-classic"


def test_unsupported_format(tmp_path: Path) -> None:
    p = tmp_path / "test.bin"
    p.write_bytes(b"\x00\x00\x00\x00garbage")
    info = detect_archive(p)
    assert info.format == "unsupported"
