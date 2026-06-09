from __future__ import annotations

from pathlib import Path

from uzpr.core.stages.protocol import Hints

# Hard-coded generic masks for lengths 6-10 when no hint info is available
_GENERIC_FALLBACK_MASKS = [
    "?a?a?a?a?a?a",
    "?a?a?a?a?a?a?a",
    "?a?a?a?a?a?a?a?a",
    "?a?a?a?a?a?a?a?a?a",
    "?a?a?a?a?a?a?a?a?a?a",
]

# Common fixed structural mask templates (length-independent patterns added first)
_COMMON_STRUCTURAL: list[str] = [
    "?l?l?l?l?d?d?d?d",
    "?u?l?l?l?l?l?d?d",
    "?l?l?l?l?l?l?d?d",
    "?u?l?l?l?d?d?d?d",
    "?l?l?l?l?d?d?d?d?s",
    "?u?l?l?l?l?d?d?s",
]


def derive_masks(hints: Hints, work_dir: Path, max_masks: int = 200) -> Path:
    """Derive hashcat mask-attack patterns from *hints* and write them to disk.

    The output file ``masks.hcmask`` is written to *work_dir*.  One mask per
    line; duplicates removed; total lines capped at *max_masks*.

    Charset-class selection rules (accumulated from hints):
    - 'lower' in must_have → ?l
    - 'upper' in must_have OR 'Capital'/'UPPER'/'camelCase' in case_styles → ?u
    - 'digit' in must_have → ?d
    - 'symbol' in must_have → ?s
    - No charset hints at all → ?a (all printable)

    For each length in [min_length, min(max_length, min_length+6)] the
    following masks are emitted (depending on which charset classes are active):
    - All-?a generic mask (always emitted)
    - Capitalised-word + 2 digits: ?u + (?l × (len-3)) + ?d?d  (if upper+lower+digit)
    - Capitalised-word + 2 digits + symbol: ?u + (?l × (len-4)) + ?d?d + ?s
      (if upper+lower+digit+symbol, length>=5)
    - All-charset-class mask: one character per active class cycling through
      ?u?l?d?s in round-robin order.

    Additionally the common structural masks from ``_COMMON_STRUCTURAL`` are
    appended if they are within the length range.

    If no length or charset information is available the five generic fallback
    masks for lengths 6-10 are written instead.

    Args:
        hints: Frozen Hints dataclass from the session.
        work_dir: Directory in which to write ``masks.hcmask``.
        max_masks: Maximum number of mask lines to write.

    Returns:
        Path to the written ``masks.hcmask`` file.
    """
    out_path = work_dir / "masks.hcmask"
    work_dir.mkdir(parents=True, exist_ok=True)

    masks: list[str] = []
    seen: set[str] = set()

    def _add(mask: str) -> None:
        if mask not in seen and len(masks) < max_masks:
            seen.add(mask)
            masks.append(mask)

    # Determine active charset classes
    use_lower = "lower" in hints.must_have
    use_upper = (
        "upper" in hints.must_have
        or any(s in ("Capital", "UPPER", "camelCase", "alternating") for s in hints.case_styles)
    )
    use_digit = "digit" in hints.must_have
    use_symbol = "symbol" in hints.must_have

    no_hints = not (use_lower or use_upper or use_digit or use_symbol)

    min_len = max(1, hints.min_length)
    max_len = min(hints.max_length, min_len + 6)  # cap to avoid explosion

    has_length_info = hints.min_length != 6 or hints.max_length != 16  # non-default

    if no_hints and not has_length_info:
        # No useful information — write generic fallback masks
        out_path.write_text("\n".join(_GENERIC_FALLBACK_MASKS) + "\n", encoding="utf-8")
        return out_path

    # Build per-length masks
    for length in range(min_len, max_len + 1):
        # Always emit a generic all-?a mask for this length
        _add("?a" * length)

        if no_hints:
            # No charset hints but we have length info — only all-?a masks
            continue

        # Build the "active charset cycle" mask: distribute charset tokens evenly
        active: list[str] = []
        if use_upper:
            active.append("?u")
        if use_lower:
            active.append("?l")
        if use_digit:
            active.append("?d")
        if use_symbol:
            active.append("?s")

        if active:
            cycle_mask = "".join(active[i % len(active)] for i in range(length))
            _add(cycle_mask)

        # Capitalised-word + 2 digits  (?u + ?l×(len-3) + ?d?d)
        if use_upper and use_lower and use_digit and length >= 4:
            lower_count = length - 3  # 1 upper + lower_count lower + 2 digit
            if lower_count >= 0:
                cap_mask = "?u" + "?l" * lower_count + "?d?d"
                _add(cap_mask)

        # Capitalised-word + 2 digits + symbol
        if use_upper and use_lower and use_digit and use_symbol and length >= 5:
            lower_count = length - 4
            if lower_count >= 0:
                cap_sym_mask = "?u" + "?l" * lower_count + "?d?d?s"
                _add(cap_sym_mask)

        # Lower + digit suffix patterns
        if use_lower and use_digit and length >= 5:
            lower_count = length - 2
            _add("?l" * lower_count + "?d?d")
            lower_count2 = length - 4
            if lower_count2 > 0:
                _add("?l" * lower_count2 + "?d?d?d?d")

        # Digit-heavy mask
        if use_digit and length >= 4:
            _add("?d" * length)

    # Append common structural masks that fit within the length range
    for structural in _COMMON_STRUCTURAL:
        # Determine the length of this mask by counting '?x' tokens
        mask_len = structural.count("?")
        if min_len <= mask_len <= hints.max_length:
            _add(structural)

    out_path.write_text("\n".join(masks) + "\n", encoding="utf-8")
    return out_path
