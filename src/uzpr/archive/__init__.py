from __future__ import annotations

from uzpr.archive.detect import ArchiveInfo, ZipEntry, RarEntry, detect_archive
from uzpr.archive.zip_inspect import pick_attack_target
from uzpr.archive.hashcat_mode import hashcat_mode_for
from uzpr.archive.zip2john import extract_zip_hash
from uzpr.archive.rar2john import extract_rar_hash

__all__ = [
    "ArchiveInfo",
    "ZipEntry",
    "RarEntry",
    "detect_archive",
    "pick_attack_target",
    "hashcat_mode_for",
    "extract_zip_hash",
    "extract_rar_hash",
]
