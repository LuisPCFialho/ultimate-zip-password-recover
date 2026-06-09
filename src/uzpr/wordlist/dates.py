from __future__ import annotations


def encode_dates(
    dates: tuple[tuple[int, int, int], ...],
    locale: str = "en-GB",
) -> list[str]:
    """Return ~40 date-string variants for each (d, m, y) tuple.

    For locale 'en-US' month-first variants are promoted; for all other
    locales day-first variants are the primary set.  Results are deduplicated.

    Args:
        dates: Sequence of (day, month, year) integer tuples.
        locale: BCP-47 locale tag controlling primary date order.

    Returns:
        Deduplicated list of date-string variants.
    """
    seen: set[str] = set()
    result: list[str] = []

    def _add(s: str) -> None:
        if s and s not in seen:
            seen.add(s)
            result.append(s)

    us_locale = locale.lower().startswith("en-us")

    for d, m, y in dates:
        dd = f"{d:02d}"
        mm = f"{m:02d}"
        yy = f"{y % 100:02d}"
        yyyy = f"{y:04d}"
        d_str = str(d)   # no leading zero
        m_str = str(m)   # no leading zero

        # Pure fragments
        _add(dd)
        _add(mm)
        _add(yy)
        _add(yyyy)
        _add(d_str)
        _add(m_str)

        # Zero-padded combinations (no separator)
        _add(dd + mm)
        _add(dd + mm + yy)
        _add(dd + mm + yyyy)
        _add(mm + dd)
        _add(mm + dd + yy)
        _add(mm + dd + yyyy)
        _add(yy + mm + dd)
        _add(yyyy + mm + dd)
        _add(yy + dd)
        _add(mm + yy)

        # Non-zero-padded combinations (no separator)
        _add(d_str + m_str)
        _add(d_str + m_str + yy)
        _add(d_str + m_str + yyyy)
        _add(m_str + d_str)
        _add(m_str + d_str + yy)
        _add(m_str + d_str + yyyy)

        # Separator variants
        for sep in ("-", ".", "/"):
            # Day-first
            _add(f"{dd}{sep}{mm}{sep}{yy}")
            _add(f"{dd}{sep}{mm}{sep}{yyyy}")
            _add(f"{d_str}{sep}{m_str}{sep}{yy}")
            _add(f"{d_str}{sep}{m_str}{sep}{yyyy}")
            # Month-first
            _add(f"{mm}{sep}{dd}{sep}{yy}")
            _add(f"{mm}{sep}{dd}{sep}{yyyy}")
            _add(f"{m_str}{sep}{d_str}{sep}{yy}")
            _add(f"{m_str}{sep}{d_str}{sep}{yyyy}")
            # Year-month-day
            _add(f"{yyyy}{sep}{mm}{sep}{dd}")
            _add(f"{yy}{sep}{mm}{sep}{dd}")

        # Locale-specific: for en-US emit month-first without separator first
        if us_locale:
            _add(mm + dd + yyyy)
            _add(mm + dd + yy)
        else:
            _add(dd + mm + yyyy)
            _add(dd + mm + yy)

    return result
