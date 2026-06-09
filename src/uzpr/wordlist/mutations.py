from __future__ import annotations

# Leet-speak substitution table: char -> list of replacements
_LEET_TABLE: dict[str, list[str]] = {
    "a": ["@", "4"],
    "e": ["3"],
    "i": ["1", "!"],
    "o": ["0"],
    "s": ["$", "5"],
    "t": ["7"],
    "l": ["1"],
}

# Maximum leet variants to generate per input string (prevents combinatorial explosion)
_LEET_CAP = 32


def case_variants(s: str) -> set[str]:
    """Return case variations of *s*.

    Variants produced:
    - original (as-is)
    - all lowercase
    - all uppercase
    - capitalize first character
    - title-case each whitespace-separated word
    - alternating case (even indices upper, odd indices lower)

    Note: leet substitutions are NOT applied here.

    Args:
        s: Input string.

    Returns:
        Set of case-variant strings (may be smaller than 6 if variants collide).
    """
    alternating = "".join(c.upper() if i % 2 == 0 else c.lower() for i, c in enumerate(s))
    return {
        s,
        s.lower(),
        s.upper(),
        s.capitalize(),
        s.title(),
        alternating,
    }


def leet_variants(s: str) -> set[str]:
    """Return leet-speak substitution variants of *s*.

    Strategy:
    1. Single substitutions: replace exactly one matching character at a time
       (one variant per substitution × number of replacement options).
    2. All-at-once substitution: replace every matching character simultaneously
       (one variant per combination of replacement choices, but capped early).

    Capped at _LEET_CAP (32) variants per input to avoid combinatorial explosion.
    All-digit strings are skipped (no leet on digit-only stems).

    Args:
        s: Input string.

    Returns:
        Set of leet-speak variants (may be empty if no substitutions apply).
    """
    if s.isdigit():
        return set()

    variants: set[str] = set()
    s_lower = s.lower()

    # Pass 1: single-character substitutions
    for idx, ch in enumerate(s_lower):
        if ch in _LEET_TABLE:
            for replacement in _LEET_TABLE[ch]:
                variant = s_lower[:idx] + replacement + s_lower[idx + 1 :]
                variants.add(variant)
                if len(variants) >= _LEET_CAP:
                    return variants

    # Pass 2: all-at-once substitutions via BFS-style expansion
    # Build list of (position, replacement) choices
    substitution_positions: list[tuple[int, list[str]]] = [
        (idx, _LEET_TABLE[ch]) for idx, ch in enumerate(s_lower) if ch in _LEET_TABLE
    ]

    if not substitution_positions:
        return variants

    # Generate combinations by iterating through replacement choices
    pending: list[str] = [s_lower]
    for idx, replacements in substitution_positions:
        next_pending: list[str] = []
        for base in pending:
            for replacement in replacements:
                candidate = base[:idx] + replacement + base[idx + 1 :]
                next_pending.append(candidate)
                variants.add(candidate)
                if len(variants) >= _LEET_CAP:
                    return variants
        pending = next_pending

    return variants


def suffix_combos(s: str, suffixes: tuple[str, ...]) -> list[str]:
    """Return *s* with each suffix from *suffixes* appended.

    Args:
        s: Base string.
        suffixes: Tuple of suffix strings to append.

    Returns:
        List of concatenated strings, one per suffix.
    """
    return [s + suffix for suffix in suffixes]


def prefix_combos(s: str, prefixes: tuple[str, ...]) -> list[str]:
    """Return *s* with each prefix from *prefixes* prepended.

    Args:
        s: Base string.
        prefixes: Tuple of prefix strings to prepend.

    Returns:
        List of concatenated strings, one per prefix.
    """
    return [prefix + s for prefix in prefixes]
