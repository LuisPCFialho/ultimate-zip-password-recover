from __future__ import annotations

import re
from pathlib import Path

from uzpr.archive.detect import ArchiveInfo

# Matches the count field in $pkzip$<count>* and $pkzip2$<count>*
_PKZIP_COUNT_RE = re.compile(r"^\$pkzip2?\$(\d+)\*")

# Matches CT= fields anywhere in the hash line — e.g. *CT=8* or *CT=0*
_CT_FIELD_RE = re.compile(r"\*CT=(\d+)\*")


def _parse_zip_classic_mode(hash_line: str) -> int | None:
    """
    Map a zip2john hash line to the correct hashcat -m mode for zip-classic archives.

    Mapping (per INTERFACES.md §3 and ARCHITECTURE.md decision tree):
      $pkzip$1*  CT=0           → 17210
      $pkzip$1*  CT=8           → 17200
      $pkzip2$3* all CT=8       → 17220
      $pkzip2$3* mixed CT       → 17225
      $pkzip2$8*                → 17230
      $zip3$...                 → None  (pkware-strong, refuse)
    """
    if hash_line.startswith("$zip3$"):
        # pkware-strong — refuse
        return None

    # Old WinZip AES format from some zip2john versions
    if hash_line.startswith("$zip$2*"):
        return 13600

    m = _PKZIP_COUNT_RE.match(hash_line)
    if m is None:
        return None

    count = int(m.group(1))

    if count == 1:
        # Single-entry hash — check the CT byte
        ct_matches = _CT_FIELD_RE.findall(hash_line)
        if ct_matches:
            ct = int(ct_matches[0])
            return 17210 if ct == 0 else 17200
        # Default to 17200 if CT field is absent
        return 17200

    if count == 3:
        ct_values = [int(v) for v in _CT_FIELD_RE.findall(hash_line)]
        if ct_values and all(v == 8 for v in ct_values):
            return 17220
        return 17225

    if count >= 8:
        return 17230

    # Counts 2, 4-7: fall back to the most generic multi-file mode
    return 17225


def hashcat_mode_for(info: ArchiveInfo, hash_file: Path) -> int | None:
    """
    Map archive info and the zip2john / rar2john hash file header to a hashcat -m mode.

    Returns None for unsupported or unrecognised formats.
    """
    fmt = info.format

    # RAR and AES-ZIP modes are fixed — no need to inspect the hash file
    if fmt == "rar3-hp":
        return 12500
    if fmt == "rar5":
        return 13000
    if fmt == "zip-aes":
        return 13600

    if fmt != "zip-classic":
        return None

    # For zip-classic we must read the hash file produced by zip2john to
    # determine the precise sub-mode.
    try:
        raw = hash_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    # zip2john output is typically "<archive_name>:<hash>"; we want the hash part.
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip the leading "<name>:" prefix that zip2john emits
        if ":" in line:
            _name, _, hash_part = line.partition(":")
            hash_line = hash_part.strip()
        else:
            hash_line = line

        if hash_line:
            return _parse_zip_classic_mode(hash_line)

    return None
