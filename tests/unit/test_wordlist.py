from __future__ import annotations

from uzpr.wordlist.dates import encode_dates
from uzpr.wordlist.filters import passes_filters
from uzpr.wordlist.mutations import case_variants, leet_variants


def test_encode_dates_basic() -> None:
    dates = ((1, 5, 1996),)  # 01/05/1996
    variants = encode_dates(dates, "en-GB")
    assert "01051996" in variants
    assert "1996" in variants
    assert "0105" in variants


def test_case_variants_lower_word() -> None:
    v = case_variants("isinho")
    assert "isinho" in v
    assert "ISINHO" in v
    assert "Isinho" in v


def test_leet_variants_capped() -> None:
    v = leet_variants("isinho")
    assert len(v) <= 32  # hard cap


def test_passes_filters_basic() -> None:
    assert passes_filters("hello1", 4, 16, frozenset())
    assert not passes_filters("hi", 4, 16, frozenset())  # too short
    assert not passes_filters("hello1", 4, 16, frozenset({"upper"}))  # missing upper


def test_passes_filters_control_chars() -> None:
    assert not passes_filters("hell\x00o", 4, 16, frozenset())
