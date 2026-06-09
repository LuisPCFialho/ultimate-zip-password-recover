from __future__ import annotations

from uzpr.archive.detect import ArchiveInfo, ZipEntry

# Deflate compression methods recognized by hashcat and bkcrack
_DEFLATE_METHODS = frozenset({8, 9})


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
