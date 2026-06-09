from __future__ import annotations

"""Build a valid ZipCrypto (PKWARE traditional) encrypted ZIP for testing.

Python's stdlib zipfile can READ ZipCrypto but cannot WRITE it, and pyzipper
only writes AES. This module implements the PKWARE traditional stream cipher so
we can create a ZipCrypto archive with a STORED (uncompressed) entry — exactly
the case bkcrack's known-plaintext attack exploits.
"""

import struct
import sys
import zlib
from pathlib import Path

# Standard CRC-32 table (PKWARE key schedule uses this).
_CRCTAB: list[int] = []
for _n in range(256):
    _c = _n
    for _ in range(8):
        _c = (0xEDB88320 ^ (_c >> 1)) if (_c & 1) else (_c >> 1)
    _CRCTAB.append(_c)


def _crc32_byte(crc: int, b: int) -> int:
    return ((crc >> 8) ^ _CRCTAB[(crc ^ b) & 0xFF]) & 0xFFFFFFFF


class _ZipCrypto:
    """PKWARE traditional encryption stream cipher."""

    def __init__(self, password: bytes) -> None:
        self.k0 = 0x12345678
        self.k1 = 0x23456789
        self.k2 = 0x34567890
        for b in password:
            self._update(b)

    def _update(self, b: int) -> None:
        self.k0 = _crc32_byte(self.k0, b)
        self.k1 = (self.k1 + (self.k0 & 0xFF)) & 0xFFFFFFFF
        self.k1 = (self.k1 * 134775813 + 1) & 0xFFFFFFFF
        self.k2 = _crc32_byte(self.k2, (self.k1 >> 24) & 0xFF)

    def _keystream_byte(self) -> int:
        t = (self.k2 | 2) & 0xFFFF
        return ((t * (t ^ 1)) >> 8) & 0xFF

    def encrypt(self, data: bytes) -> bytes:
        out = bytearray()
        for b in data:
            c = self._keystream_byte()
            out.append(b ^ c)
            self._update(b)
        return bytes(out)


def build_zipcrypto(path: Path, entry_name: str, content: bytes, password: bytes) -> Path:
    """Write a ZipCrypto archive containing one STORED (uncompressed) entry."""
    crc = zlib.crc32(content) & 0xFFFFFFFF

    # 12-byte encryption header: 11 random-ish bytes + final byte = CRC high byte.
    # The decrypted header's last byte must equal (crc >> 24) for the integrity
    # check (this is the one guaranteed known byte bkcrack auto-loads).
    header_plain = bytes((i * 37 + 11) & 0xFF for i in range(11)) + bytes([(crc >> 24) & 0xFF])

    cipher = _ZipCrypto(password)
    enc_header = cipher.encrypt(header_plain)
    enc_content = cipher.encrypt(content)
    encrypted_blob = enc_header + enc_content

    name_b = entry_name.encode()
    comp_size = len(encrypted_blob)  # STORED: compressed == stored size (incl. 12-byte header)
    uncomp_size = len(content)

    # GP flag bit 0 = encrypted. Method 0 = STORED.
    gp_flag = 0x0001
    method = 0

    # --- Local file header ---
    local_header = struct.pack(
        "<4sHHHHHIIIHH",
        b"PK\x03\x04",
        20,  # version needed
        gp_flag,
        method,
        0,  # mod time
        0,  # mod date
        crc,
        comp_size,
        uncomp_size,
        len(name_b),
        0,  # extra len
    )
    local_offset = 0
    local_record = local_header + name_b + encrypted_blob

    # --- Central directory header ---
    central = struct.pack(
        "<4sHHHHHHIIIHHHHHII",
        b"PK\x01\x02",
        20,  # version made by
        20,  # version needed
        gp_flag,
        method,
        0,
        0,
        crc,
        comp_size,
        uncomp_size,
        len(name_b),
        0,  # extra len
        0,  # comment len
        0,  # disk number
        0,  # internal attrs
        0,  # external attrs
        local_offset,
    )
    central_record = central + name_b

    # --- End of central directory ---
    cd_offset = len(local_record)
    cd_size = len(central_record)
    eocd = struct.pack(
        "<4sHHHHIIH",
        b"PK\x05\x06",
        0,
        0,
        1,
        1,
        cd_size,
        cd_offset,
        0,
    )

    path.write_bytes(local_record + central_record + eocd)
    return path


def make_png(min_len: int = 64) -> bytes:
    """A byte blob whose first 16 bytes are the deterministic PNG signature + IHDR."""
    head = bytes(
        [
            0x89,
            0x50,
            0x4E,
            0x47,
            0x0D,
            0x0A,
            0x1A,
            0x0A,
            0x00,
            0x00,
            0x00,
            0x0D,
            0x49,
            0x48,
            0x44,
            0x52,
        ]
    )
    body = b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00" + b"PADDING" * 8
    blob = head + body
    return blob.ljust(min_len, b"\x00")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("test_zipcrypto_png.zip")
    pw = sys.argv[2].encode() if len(sys.argv) > 2 else b"rT5#uY8@vW1$"
    build_zipcrypto(out, "image.png", make_png(80), pw)
    print(f"Wrote {out} ({out.stat().st_size} bytes), password={pw!r}")
