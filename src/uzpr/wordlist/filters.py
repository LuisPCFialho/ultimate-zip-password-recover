from __future__ import annotations


def passes_filters(
    s: str,
    min_len: int,
    max_len: int,
    must_have: frozenset[str],
) -> bool:
    """Return True if *s* passes all candidate-quality rules.

    Rules applied in order (short-circuit on first failure):
    - Non-empty string.
    - Not all-whitespace.
    - No control characters (ord < 32, excluding space ord==32).
    - Length >= 4 (hard minimum regardless of min_len).
    - Length within [min_len, max_len].
    - If 'digit' in must_have: at least one decimal digit.
    - If 'upper' in must_have: at least one uppercase letter.
    - If 'lower' in must_have: at least one lowercase letter.
    - If 'symbol' in must_have: at least one non-alphanumeric character.

    Args:
        s: Candidate password string.
        min_len: Minimum acceptable length (from Hints).
        max_len: Maximum acceptable length (from Hints).
        must_have: Frozenset of required character class names
                   ('digit', 'upper', 'lower', 'symbol').

    Returns:
        True if *s* passes every rule, False otherwise.
    """
    if not s:
        return False

    if s.isspace():
        return False

    # Reject control characters (ord < 32, space = 32 is allowed)
    for ch in s:
        if ord(ch) < 32:
            return False

    length = len(s)

    # Hard minimum of 4
    if length < 4:
        return False

    # Caller-supplied length range
    if length < min_len or length > max_len:
        return False

    # Required character-class checks
    if "digit" in must_have and not any(c.isdigit() for c in s):
        return False

    if "upper" in must_have and not any(c.isupper() for c in s):
        return False

    if "lower" in must_have and not any(c.islower() for c in s):
        return False

    return not ("symbol" in must_have and not any(not c.isalnum() for c in s))
