from __future__ import annotations

import asyncio
from pathlib import Path

from uzpr.core.dedup import BloomFilter
from uzpr.core.stages.protocol import Hints
from uzpr.wordlist.dates import encode_dates
from uzpr.wordlist.filters import passes_filters
from uzpr.wordlist.mutations import case_variants, leet_variants, suffix_combos

# Default suffixes used when hints carry none
_DEFAULT_SUFFIXES: tuple[str, ...] = (
    "", ".", "!", "1", "12", "123", "1234", "0", "01", "!",
)

# Symbols used for Tier-D injection
_INJECT_SYMBOLS = "!@#$."


async def generate(
    hints: Hints,
    work_dir: Path,
    cap: int = 10_000_000,
) -> Path:
    """Generate a tiered smart wordlist from *hints* and write it to disk.

    Candidates are streamed through four tiers (A → D) in priority order and
    deduplicated via an mmap-backed Bloom filter.  Generation stops when the
    total candidate count reaches *cap*.

    The output file ``stage3.wordlist`` is written to *work_dir* (UTF-8,
    one candidate per line).

    If all personal-data fields in *hints* are empty an empty file is written
    immediately.

    Tier summary
    ------------
    A (~0.5 % of cap): raw seeds + raw date fragments; no mutation.
    B (~5 %):  seeds × case_variants × top-10 suffixes.
    C (~20 %): seeds × case × dates × suffixes × prefixes;
               date_frag × suffix (catches "0501961423" reference pattern).
    D (~75 %): leet on seeds; double-seed concatenation; symbol injection.

    Control is yielded to the event loop every 10 000 candidates so the
    generator remains cooperative inside an asyncio task.

    Args:
        hints: Frozen Hints dataclass describing the target password space.
        work_dir: Session working directory; both the wordlist and the Bloom
                  filter are written here.
        cap: Hard upper bound on emitted candidates (default 10 000 000).

    Returns:
        Absolute path to the written ``stage3.wordlist`` file.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    out_path = work_dir / "stage3.wordlist"

    # Guard: if no personal-data fields provided, write empty file
    all_empty = (
        not hints.stems
        and not hints.dates
        and not hints.first_names
        and not hints.surnames
        and not hints.nicknames
        and not hints.pet_names
        and not hints.places
    )
    if all_empty:
        out_path.write_bytes(b"")
        return out_path

    # Build seed set: all personal word tokens
    seeds: list[str] = list(
        hints.stems
        + hints.first_names
        + hints.surnames
        + hints.nicknames
        + hints.pet_names
        + hints.places
    )

    # Date string fragments
    date_frags: list[str] = encode_dates(hints.dates, hints.locale) if hints.dates else []

    # Suffix / prefix lists
    suffixes: tuple[str, ...] = hints.suffixes[:10] if hints.suffixes else _DEFAULT_SUFFIXES
    prefixes: tuple[str, ...] = hints.prefixes if hints.prefixes else ()

    # Bloom filter for deduplication
    bloom = BloomFilter(
        path=work_dir / "stage3.bloom",
        capacity=cap,
        fp_rate=0.001,
    )

    count = 0
    tier_caps = {
        "A": max(1, int(cap * 0.005)),
        "B": max(1, int(cap * 0.05)),
        "C": max(1, int(cap * 0.20)),
        # Tier D uses the remainder up to cap
    }

    async def _emit(candidate: str) -> bool:
        """Filter, dedup, and write a single candidate.

        Returns True if the candidate was written (count was incremented).
        """
        nonlocal count
        if not passes_filters(candidate, hints.min_length, hints.max_length, hints.must_have):
            return False
        if candidate in bloom:
            return False
        bloom.add(candidate)
        fh.write(candidate + "\n")
        count += 1
        return True

    with out_path.open("w", encoding="utf-8") as fh:

        # ------------------------------------------------------------------ #
        # Tier A: raw seeds + raw date fragments
        # ------------------------------------------------------------------ #
        tier_a_limit = tier_caps["A"]
        tier_a_count = 0

        for token in seeds:
            if count >= cap or tier_a_count >= tier_a_limit:
                break
            if await _emit(token):
                tier_a_count += 1
            if count % 10_000 == 0:
                await asyncio.sleep(0)

        for frag in date_frags:
            if count >= cap or tier_a_count >= tier_a_limit:
                break
            if await _emit(frag):
                tier_a_count += 1
            if count % 10_000 == 0:
                await asyncio.sleep(0)

        # ------------------------------------------------------------------ #
        # Tier B: seeds × case_variants × top-10 suffixes
        # ------------------------------------------------------------------ #
        tier_b_limit = tier_caps["B"]
        tier_b_count = 0

        for seed in seeds:
            if count >= cap or tier_b_count >= tier_b_limit:
                break
            for variant in case_variants(seed):
                if count >= cap or tier_b_count >= tier_b_limit:
                    break
                # Emit the variant itself
                if await _emit(variant):
                    tier_b_count += 1
                # Emit variant + suffix
                for cand in suffix_combos(variant, suffixes):
                    if count >= cap or tier_b_count >= tier_b_limit:
                        break
                    if await _emit(cand):
                        tier_b_count += 1
                    if count % 10_000 == 0:
                        await asyncio.sleep(0)

        # ------------------------------------------------------------------ #
        # Tier C: seeds × case × dates × suffixes × prefixes
        #         + date_frag × suffix
        # ------------------------------------------------------------------ #
        tier_c_limit = tier_caps["C"]
        tier_c_count = 0

        # C1: seed × case × date_frag × suffix × prefix
        for seed in seeds:
            if count >= cap or tier_c_count >= tier_c_limit:
                break
            for variant in case_variants(seed):
                if count >= cap or tier_c_count >= tier_c_limit:
                    break
                for frag in date_frags:
                    if count >= cap or tier_c_count >= tier_c_limit:
                        break
                    base = variant + frag
                    for suf in suffixes:
                        if count >= cap or tier_c_count >= tier_c_limit:
                            break
                        cand = base + suf
                        if await _emit(cand):
                            tier_c_count += 1
                        # With prefix too
                        for pre in prefixes:
                            if count >= cap or tier_c_count >= tier_c_limit:
                                break
                            if await _emit(pre + cand):
                                tier_c_count += 1
                        if count % 10_000 == 0:
                            await asyncio.sleep(0)

        # C2: date_frag × suffix only (catches "0501961423" reference case)
        for frag in date_frags:
            if count >= cap or tier_c_count >= tier_c_limit:
                break
            for suf in suffixes:
                if count >= cap or tier_c_count >= tier_c_limit:
                    break
                if await _emit(frag + suf):
                    tier_c_count += 1
                if count % 10_000 == 0:
                    await asyncio.sleep(0)

        # ------------------------------------------------------------------ #
        # Tier D: leet variants + double-seed concat + symbol injection
        # ------------------------------------------------------------------ #
        # D1: leet variants
        for seed in seeds:
            if count >= cap:
                break
            for leet in leet_variants(seed):
                if count >= cap:
                    break
                await _emit(leet)
                if count % 10_000 == 0:
                    await asyncio.sleep(0)

        # D2: double-seed concatenation
        for i, s1 in enumerate(seeds):
            if count >= cap:
                break
            for j, s2 in enumerate(seeds):
                if count >= cap:
                    break
                if i == j:
                    continue
                await _emit(s1 + s2)
                if count % 10_000 == 0:
                    await asyncio.sleep(0)

        # D3: symbol injection at positions 0, -1, and after index 3
        for seed in seeds:
            if count >= cap:
                break
            for sym in _INJECT_SYMBOLS:
                if count >= cap:
                    break
                # Prepend
                await _emit(sym + seed)
                # Append
                await _emit(seed + sym)
                # Insert after position 3 (if string long enough)
                if len(seed) > 3:
                    await _emit(seed[:3] + sym + seed[3:])
                if count % 10_000 == 0:
                    await asyncio.sleep(0)

    bloom.close()
    return out_path


def estimate_count(hints: Hints) -> int:
    """Return a cheap upper-bound estimate of candidate count for UI display.

    Computes: seeds_with_variants × date_variants × (suffixes+1) × (prefixes+1).
    Capped at 10 000 000.

    No file I/O is performed.

    Args:
        hints: Frozen Hints dataclass.

    Returns:
        Upper-bound estimate capped at 10 000 000.
    """
    seeds = list(
        hints.stems
        + hints.first_names
        + hints.surnames
        + hints.nicknames
        + hints.pet_names
        + hints.places
    )

    if not seeds and not hints.dates:
        return 0

    # Each seed produces up to 6 case variants
    seeds_with_variants = len(seeds) * 6

    # Date variants: ~40 per date tuple (conservative estimate)
    date_variants = len(hints.dates) * 40

    # +1 for the "no suffix / no prefix" case
    suffix_factor = len(hints.suffixes[:10]) + 1 if hints.suffixes else len(_DEFAULT_SUFFIXES) + 1
    prefix_factor = len(hints.prefixes) + 1 if hints.prefixes else 1

    estimate = seeds_with_variants * max(date_variants, 1) * suffix_factor * prefix_factor

    return min(estimate, 10_000_000)
