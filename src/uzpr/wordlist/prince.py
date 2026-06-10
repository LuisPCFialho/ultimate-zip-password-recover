from __future__ import annotations

from pathlib import Path


def build_prince_elements(
    stems: list[str],
    top_dict: Path,
    out: Path,
    extra_words: list[str] | None = None,
) -> None:
    """Build a PRINCE elements file from personal stems and a top-dictionary.

    Personal *stems* are written first (highest priority), then any
    *extra_words*, followed by lines from *top_dict*. When *stems* is empty
    we pull up to 500 lines from *top_dict* (unhinted fallback); otherwise
    up to 1 000 lines are appended after the stems.

    Args:
        stems: Personal word stems from the user's hints (Hints.stems etc.).
        top_dict: Path to a background dictionary file (e.g. rockyou.txt).
        out: Output path for the elements file.
        extra_words: Optional additional words to include after stems.
    """
    out.parent.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    lines: list[str] = []

    for stem in stems:
        clean = stem.strip()
        if clean and clean not in seen:
            seen.add(clean)
            lines.append(clean)

    if extra_words:
        for word in extra_words:
            clean = word.strip()
            if clean and clean not in seen:
                seen.add(clean)
                lines.append(clean)

    # When no stems were provided this is an unhinted run -- pull a smaller
    # 500-word slice as the entire element pool.
    limit = 500 if not stems else 1000

    if top_dict.exists():
        count = 0
        with top_dict.open(encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                if count >= limit:
                    break
                word = raw_line.rstrip("\r\n")
                if word and word not in seen:
                    seen.add(word)
                    lines.append(word)
                    count += 1

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
