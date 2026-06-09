from __future__ import annotations

"""File-type magic signatures for ZipCrypto known-plaintext attacks.

The Biham-Kocher known-plaintext attack (implemented in ``bkcrack``) recovers
the three internal ZipCrypto keys from a single ciphertext/plaintext pair,
regardless of the password's length or charset. It requires **>= 12 known
plaintext bytes** (with **>= 8 contiguous**) for one entry.

For a **STORED** (method 0, uncompressed) entry, the first bytes of the
encrypted stream correspond exactly to the file's deterministic magic header,
so those bytes are known plaintext "for free". A **DEFLATE**-compressed entry
does *not* qualify: compression scrambles the leading bytes, so the raw magic
header is no longer present at offset 0.

This module maps file extensions to their deterministic magic prefixes. Only
signatures whose magic is **>= 12 bytes** are "usable" for a zero-input attack
(see :func:`usable_signatures`); shorter signatures are retained for reference
and detection but cannot satisfy bkcrack's minimum on their own.
"""

from dataclasses import dataclass

# Minimum number of known plaintext bytes bkcrack needs for one entry.
_MIN_KNOWN_BYTES = 12


@dataclass(frozen=True, slots=True)
class Signature:
    name: str
    extensions: tuple[str, ...]
    magic: bytes
    description: str


# Ordered by descending magic length so longer (more deterministic) signatures
# are preferred when an extension is shared. ``signature_for`` does not rely on
# ordering, but keeping it sorted documents intent.
_SIGNATURES: tuple[Signature, ...] = (
    Signature(
        name="png",
        extensions=(".png",),
        # PNG signature (8) + first IHDR chunk header (length + "IHDR").
        magic=bytes.fromhex("89504E470D0A1A0A0000000D49484452"),
        description="PNG signature + IHDR chunk header (16 bytes)",
    ),
    Signature(
        name="elf",
        extensions=(".elf", ".so", ".o"),
        # ELF magic + EI_CLASS=64bit, EI_DATA=LE, EI_VERSION=1 + padding.
        magic=bytes.fromhex("7F454C46020101000000000000000000"),
        description="ELF 64-bit little-endian header + padding (16 bytes)",
    ),
    Signature(
        name="ole",
        extensions=(".doc", ".xls", ".ppt", ".msi"),
        magic=bytes.fromhex("D0CF11E0A1B11AE1"),
        description="OLE2 compound document header (8 bytes)",
    ),
    Signature(
        name="pdf",
        extensions=(".pdf",),
        magic=b"%PDF-1.",
        description="PDF document header (7 bytes)",
    ),
    Signature(
        name="gif",
        extensions=(".gif",),
        magic=b"GIF89a",
        description="GIF89a header (6 bytes)",
    ),
    Signature(
        name="zip",
        extensions=(".zip", ".docx", ".xlsx", ".pptx", ".jar", ".apk", ".odt"),
        magic=bytes.fromhex("504B0304"),
        description="ZIP local file header signature (4 bytes)",
    ),
    Signature(
        name="class",
        extensions=(".class",),
        magic=bytes.fromhex("CAFEBABE"),
        description="Java class file magic (4 bytes)",
    ),
)


def signature_for(filename: str) -> Signature | None:
    """Return the :class:`Signature` matching *filename*'s extension, or None.

    The extension match is case-insensitive. If multiple signatures match the
    same extension, the one with the longest ``magic`` is preferred (more
    deterministic known plaintext is always better for bkcrack).
    """
    lowered = filename.lower()
    best: Signature | None = None
    for sig in _SIGNATURES:
        if any(lowered.endswith(ext) for ext in sig.extensions):
            if best is None or len(sig.magic) > len(best.magic):
                best = sig
    return best


def usable_signatures() -> tuple[Signature, ...]:
    """Return only signatures with >= 12 magic bytes (bkcrack's minimum)."""
    return tuple(sig for sig in _SIGNATURES if len(sig.magic) >= _MIN_KNOWN_BYTES)
