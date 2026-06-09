from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ZipEntry:
    name: str
    size: int
    compressed_size: int
    method: int
    crc32: int
    encrypted: bool


@dataclass(frozen=True, slots=True)
class RarEntry:
    name: str
    size: int
    compressed_size: int
    encrypted: bool


@dataclass(frozen=True, slots=True)
class ArchiveInfo:
    path: Path
    format: str  # 'zip-classic'|'zip-aes'|'rar3-hp'|'rar5'|'pkware-strong'|'plain'|'unsupported'
    entries: tuple[ZipEntry | RarEntry, ...]
    aes_strength: int | None  # 128|192|256 if zip-aes
    header_encrypted: bool  # rar3 -hp


_ZIP_LOCAL_SIG = b"PK\x03\x04"
_RAR3_SIG = b"Rar!\x1a\x07\x00"
_RAR5_SIG = b"Rar!\x1a\x07\x01\x00"

_AES_STRENGTH_MAP: dict[int, int] = {1: 128, 2: 192, 3: 256}


def _walk_zip_extra(extra: bytes) -> tuple[int, int] | None:
    """Walk extra field blocks; return (vendor_version, strength) for AES tag 0x9901, or None."""
    offset = 0
    while offset + 4 <= len(extra):
        tag, size = struct.unpack_from("<HH", extra, offset)
        offset += 4
        data = extra[offset : offset + size]
        offset += size
        if tag == 0x9901 and len(data) >= 7:
            vendor_version = struct.unpack_from("<H", data, 0)[0]
            vendor_id = data[2:4]
            strength = data[4]
            if vendor_id == b"AE" and strength in _AES_STRENGTH_MAP:
                return vendor_version, strength
    return None


def _detect_zip_format(data: bytes) -> tuple[str, int | None]:
    """
    Walk ZIP local file headers to determine the encryption format.

    Returns (format_string, aes_strength_or_None).
    """
    offset = 0
    format_result: str = "plain"
    aes_strength: int | None = None

    while offset + 30 <= len(data):
        sig = data[offset : offset + 4]
        if sig != _ZIP_LOCAL_SIG:
            break

        (
            _sig,
            _version_needed,
            gp_flag,
            method,
            _mod_time,
            _mod_date,
            _crc32,
            _compressed_size,
            _uncompressed_size,
            fname_len,
            extra_len,
        ) = struct.unpack_from("<4sHHHHHIIIHH", data, offset)

        fname_offset = offset + 30
        extra_offset = fname_offset + fname_len
        next_header = extra_offset + extra_len

        encrypted = bool(gp_flag & 0x0001)
        strong = bool(gp_flag & 0x0040)

        if strong:
            return "pkware-strong", None

        if not encrypted:
            format_result = "plain"
            offset = next_header
            continue

        # Encrypted entry — check method
        if method == 99:
            extra_data = data[extra_offset : extra_offset + extra_len]
            aes_info = _walk_zip_extra(extra_data)
            if aes_info is not None:
                _vendor_version, strength_byte = aes_info
                aes_strength = _AES_STRENGTH_MAP.get(strength_byte)
                return "zip-aes", aes_strength
            # method 99 without valid AES extra — treat as unknown
            return "unsupported", None

        # Standard ZipCrypto
        format_result = "zip-classic"
        offset = next_header

    return format_result, aes_strength


def _build_zip_entries(path: Path) -> tuple[ZipEntry, ...]:
    """Use pyzipper to enumerate ZIP entries; return empty tuple on any failure."""
    try:
        import pyzipper  # type: ignore[import-untyped]

        entries: list[ZipEntry] = []
        with pyzipper.AESZipFile(path, "r") as zf:
            for info in zf.infolist():
                encrypted = bool(info.flag_bits & 0x1)
                entries.append(
                    ZipEntry(
                        name=info.filename,
                        size=info.file_size,
                        compressed_size=info.compress_size,
                        method=info.compress_type,
                        crc32=info.CRC,
                        encrypted=encrypted,
                    )
                )
        return tuple(entries)
    except Exception:
        return ()


def _build_rar_entries(path: Path) -> tuple[RarEntry, ...]:
    """Use rarfile to enumerate RAR entries; return empty tuple on any failure."""
    try:
        import rarfile  # type: ignore[import-untyped]

        entries: list[RarEntry] = []
        with rarfile.RarFile(path) as rf:
            for info in rf.infolist():
                entries.append(
                    RarEntry(
                        name=info.filename,
                        size=info.file_size,
                        compressed_size=info.compress_size,
                        encrypted=info.needs_password(),
                    )
                )
        return tuple(entries)
    except Exception:
        return ()


def detect_archive(path: Path) -> ArchiveInfo:
    """
    Detect archive format by reading raw bytes (never relies on file extension).

    Returns an ArchiveInfo with format, entries, aes_strength, and header_encrypted.
    """
    raw = path.read_bytes()
    header = raw[:8]

    # RAR5 — check 8-byte sig first (superset of RAR3 7-byte sig)
    if header == _RAR5_SIG:
        entries = _build_rar_entries(path)
        return ArchiveInfo(
            path=path,
            format="rar5",
            entries=entries,
            aes_strength=None,
            header_encrypted=False,
        )

    # RAR3 — 7-byte sig
    if header[:7] == _RAR3_SIG:
        # Main archive block starts at offset 7.
        # Block layout: HEAD_CRC(2) HEAD_TYPE(1) HEAD_FLAGS(2) HEAD_SIZE(2)
        # For MAIN_HEAD (type 0x73), archive flags are HEAD_FLAGS.
        # Flag 0x0080 = volume is encrypted (header encrypted / -hp).
        header_encrypted = False
        if len(raw) >= 13:
            head_flags = struct.unpack_from("<H", raw, 9)[0]
            header_encrypted = bool(head_flags & 0x0080)
        entries = _build_rar_entries(path)
        return ArchiveInfo(
            path=path,
            format="rar3-hp",
            entries=entries,
            aes_strength=None,
            header_encrypted=header_encrypted,
        )

    # ZIP family — 4-byte sig
    if header[:4] == _ZIP_LOCAL_SIG:
        fmt, aes_strength = _detect_zip_format(raw)
        entries: tuple[ZipEntry | RarEntry, ...] = _build_zip_entries(path)
        return ArchiveInfo(
            path=path,
            format=fmt,
            entries=entries,
            aes_strength=aes_strength,
            header_encrypted=False,
        )

    return ArchiveInfo(
        path=path,
        format="unsupported",
        entries=(),
        aes_strength=None,
        header_encrypted=False,
    )
