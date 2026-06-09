from __future__ import annotations

from uzpr.archive.detect import ArchiveInfo, ZipEntry
from uzpr.archive.signatures import signature_for, usable_signatures

# Deflate compression methods recognized by hashcat and bkcrack
_DEFLATE_METHODS = frozenset({8, 9})

# ZIP STORED (uncompressed) compression method.
_STORED_METHOD = 0


def pick_attack_target(info: ArchiveInfo) -> str | None:
    """
    Return the name of the smallest deflated encrypted ZIP entry (best for hashcat/bkcrack).

    Preference order:
    1. Smallest encrypted entry that uses deflate (method 8 or 9).
    2. Smallest encrypted entry of any method if no deflated entries exist.
    3. None if there are no encrypted entries at all.
    """
    encrypted_entries: list[ZipEntry] = [
        e for e in info.entries if isinstance(e, ZipEntry) and e.encrypted
    ]
    if not encrypted_entries:
        return None

    deflated = [e for e in encrypted_entries if e.method in _DEFLATE_METHODS]
    candidates = deflated if deflated else encrypted_entries

    best = min(candidates, key=lambda e: e.compressed_size)
    return best.name


def find_known_plaintext_target(info: ArchiveInfo) -> tuple[str, bytes] | None:
    """
    Find a STORED encrypted entry whose magic header is usable known plaintext.

    Only **STORED** (method 0, uncompressed) entries qualify: their first
    ciphertext bytes correspond exactly to the file's deterministic magic
    header. DEFLATE-compressed entries scramble the leading bytes, so their raw
    magic header is not present at offset 0 and cannot serve as known plaintext.

    For each encrypted STORED entry, the file extension is matched against the
    signature table. A candidate qualifies only if its signature is "usable"
    (magic length >= 12 bytes, bkcrack's minimum). Among all candidates, the one
    exposing the MOST deterministic bytes (longest magic) is returned.

    Returns ``(entry_name, magic_bytes)`` for the best candidate, or ``None`` if
    no encrypted STORED entry maps to a usable signature.
    """
    usable_names = {sig.name for sig in usable_signatures()}

    best_name: str | None = None
    best_magic: bytes = b""
    for entry in info.entries:
        if not isinstance(entry, ZipEntry):
            continue
        if not entry.encrypted or entry.method != _STORED_METHOD:
            continue
        sig = signature_for(entry.name)
        if sig is None or sig.name not in usable_names:
            continue
        if len(sig.magic) > len(best_magic):
            best_name = entry.name
            best_magic = sig.magic

    if best_name is None:
        return None
    return best_name, best_magic
