from __future__ import annotations

from uzpr.archive.detect import ArchiveInfo, RarEntry, ZipEntry, detect_archive
from uzpr.archive.hashcat_mode import hashcat_mode_for
from uzpr.archive.rar2john import extract_rar_hash
from uzpr.archive.zip2john import extract_zip_hash
from uzpr.archive.zip_inspect import pick_attack_target

__all__ = [
    "ArchiveInfo",
    "RarEntry",
    "ZipEntry",
    "detect_archive",
    "extract_rar_hash",
    "extract_zip_hash",
    "hashcat_mode_for",
    "pick_attack_target",
]
