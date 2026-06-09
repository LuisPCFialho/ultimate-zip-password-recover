from __future__ import annotations

from pathlib import Path


def build_prince_elements(
    stems: list[str],
    top_dict: Path,
    out: Path,
) -> None:
    """Build a PRINCE elements file from personal stems and a top-dictionary.

    The elements file is a plain-text file with one word per line used as
    input for the ``pp64`` (PRINCE) attack.  Personal *stems* are written
    first (highest priority), followed by up to 1 000 lines from *top_dict*
    that are not already present in *stems*.

    Args:
        stems: Personal word stems from the user's hints (Hints.stems etc.).
        top_dict: Path to a background dictionary file (e.g. rockyou.txt).
        out: Output path for the elements file.
    """
    out.parent.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    lines: list[str] = []

    for stem in stems:
        clean = stem.strip()
        if clean and clean not in seen:
            seen.add(clean)
            lines.append(clean)

    if top_dict.exists():
        count = 0
        with top_dict.open(encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                if count >= 1000:
                    break
                word = raw_line.rstrip("\r\n")
                if word and word not in seen:
                    seen.add(word)
                    lines.append(word)
                    count += 1

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
