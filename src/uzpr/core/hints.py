from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any

from uzpr.core.stages.protocol import Hints

# Field metadata: maps field name -> expected container type after deserialization.
# 'tuple'     -> list in JSON, reconstruct as tuple
# 'frozenset' -> list in JSON, reconstruct as frozenset
# 'path'      -> str in JSON, reconstruct as Path (or None)
_FIELD_TYPES: dict[str, str] = {
    "dates": "tuple",
    "first_names": "tuple",
    "surnames": "tuple",
    "nicknames": "tuple",
    "pet_names": "tuple",
    "places": "tuple",
    "stems": "tuple",
    "suffixes": "tuple",
    "prefixes": "tuple",
    "case_styles": "tuple",
    "must_have": "frozenset",
    "plaintext_sample": "path",
}


def _nfc(s: str) -> str:
    """Return NFC-normalized, whitespace-stripped string."""
    return unicodedata.normalize("NFC", s).strip()


def _dedup_ordered(items: list[str]) -> list[str]:
    """Deduplicate a list preserving first-occurrence order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def normalize_hints(raw: dict[str, Any]) -> Hints:
    """Normalize a raw dict (from UI form) into a Hints instance.

    For every tuple field: NFC-normalize each string, strip whitespace,
    filter empty strings, deduplicate preserving insertion order.
    For frozenset fields: same treatment.
    For Path fields: resolve the path.
    For int/str scalars: coerce to the appropriate type.
    """

    def _norm_str_seq(value: Any) -> list[str]:
        if not value:
            return []
        items = [_nfc(s) for s in value if isinstance(s, str)]
        items = [s for s in items if s]
        return _dedup_ordered(items)

    dates_raw = raw.get("dates", ())
    normalized_dates: list[tuple[int, int, int]] = []
    seen_dates: set[tuple[int, int, int]] = set()
    for entry in dates_raw:
        try:
            d, m, y = int(entry[0]), int(entry[1]), int(entry[2])
            t = (d, m, y)
            if t not in seen_dates:
                seen_dates.add(t)
                normalized_dates.append(t)
        except (TypeError, ValueError, IndexError):
            pass

    plaintext_raw = raw.get("plaintext_sample")
    plaintext: Path | None = Path(plaintext_raw).resolve() if plaintext_raw else None

    must_have_raw = raw.get("must_have", [])
    must_have_items = [_nfc(s) for s in must_have_raw if isinstance(s, str)]
    must_have_items = [s for s in must_have_items if s]

    return Hints(
        full_password=str(raw["full_password"]).strip() if raw.get("full_password") else None,
        partial_mask=str(raw["partial_mask"]).strip() if raw.get("partial_mask") else None,
        dates=tuple(normalized_dates),
        first_names=tuple(_norm_str_seq(raw.get("first_names", ()))),
        surnames=tuple(_norm_str_seq(raw.get("surnames", ()))),
        nicknames=tuple(_norm_str_seq(raw.get("nicknames", ()))),
        pet_names=tuple(_norm_str_seq(raw.get("pet_names", ()))),
        places=tuple(_norm_str_seq(raw.get("places", ()))),
        stems=tuple(_norm_str_seq(raw.get("stems", ()))),
        suffixes=tuple(_norm_str_seq(raw.get("suffixes", ()))),
        prefixes=tuple(_norm_str_seq(raw.get("prefixes", ()))),
        case_styles=tuple(_norm_str_seq(raw.get("case_styles", ()))),
        must_have=frozenset(must_have_items),
        min_length=int(raw.get("min_length", 6)),
        max_length=int(raw.get("max_length", 16)),
        locale=str(raw.get("locale", "en-GB")),
        plaintext_sample=plaintext,
    )


class _HintsEncoder(json.JSONEncoder):
    """JSON encoder that handles frozenset, tuple, and Path."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, frozenset):
            return list(obj)
        if isinstance(obj, Path):
            return str(obj)
        return super().default(obj)

    def encode(self, obj: Any) -> str:
        # tuples are indistinguishable from lists in json.JSONEncoder.default,
        # so we pre-convert the Hints dataclass to a plain dict with tagged values.
        return super().encode(obj)


def _hints_to_dict(h: Hints) -> dict[str, Any]:
    """Convert Hints to a JSON-serializable dict."""
    return {
        "full_password": h.full_password,
        "partial_mask": h.partial_mask,
        "dates": [list(d) for d in h.dates],
        "first_names": list(h.first_names),
        "surnames": list(h.surnames),
        "nicknames": list(h.nicknames),
        "pet_names": list(h.pet_names),
        "places": list(h.places),
        "stems": list(h.stems),
        "suffixes": list(h.suffixes),
        "prefixes": list(h.prefixes),
        "case_styles": list(h.case_styles),
        "must_have": list(h.must_have),
        "min_length": h.min_length,
        "max_length": h.max_length,
        "locale": h.locale,
        "plaintext_sample": str(h.plaintext_sample) if h.plaintext_sample else None,
    }


def serialize_hints(h: Hints) -> bytes:
    """Serialize Hints to JSON bytes (for DPAPI encryption)."""
    return json.dumps(_hints_to_dict(h), ensure_ascii=False).encode("utf-8")


def deserialize_hints(b: bytes) -> Hints:
    """Deserialize Hints from JSON bytes."""
    raw: dict[str, Any] = json.loads(b.decode("utf-8"))

    dates_raw = raw.get("dates", [])
    dates: tuple[tuple[int, int, int], ...] = tuple(
        (int(d[0]), int(d[1]), int(d[2])) for d in dates_raw
    )

    plaintext_raw = raw.get("plaintext_sample")
    plaintext: Path | None = Path(plaintext_raw) if plaintext_raw else None

    return Hints(
        full_password=raw.get("full_password"),
        partial_mask=raw.get("partial_mask"),
        dates=dates,
        first_names=tuple(raw.get("first_names", [])),
        surnames=tuple(raw.get("surnames", [])),
        nicknames=tuple(raw.get("nicknames", [])),
        pet_names=tuple(raw.get("pet_names", [])),
        places=tuple(raw.get("places", [])),
        stems=tuple(raw.get("stems", [])),
        suffixes=tuple(raw.get("suffixes", [])),
        prefixes=tuple(raw.get("prefixes", [])),
        case_styles=tuple(raw.get("case_styles", [])),
        must_have=frozenset(raw.get("must_have", [])),
        min_length=int(raw.get("min_length", 6)),
        max_length=int(raw.get("max_length", 16)),
        locale=str(raw.get("locale", "en-GB")),
        plaintext_sample=plaintext,
    )
