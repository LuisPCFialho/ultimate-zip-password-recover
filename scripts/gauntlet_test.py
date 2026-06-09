from __future__ import annotations

import io
import sys

# Force UTF-8 output on Windows to support unicode characters in progress lines
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

"""
Gauntlet test — 30 ZIPs with escalating password difficulty.

Runs the UZPR cascade on each archive and reports which stage found
the password, how long it took, and marks failures clearly.

Usage:
    python scripts/gauntlet_test.py
    python scripts/gauntlet_test.py --stop-on-fail
    python scripts/gauntlet_test.py --stages 1,3,4  # only run specific stages
    python scripts/gauntlet_test.py --from 10        # resume from test 10
"""

import argparse
import asyncio
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pyzipper

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# ---------------------------------------------------------------------------
# Password difficulty ladder
# ---------------------------------------------------------------------------
# Each entry: (label, password, hints_dict, expected_stage)
# hints_dict keys: stems, dates (as (d,m,y) tuples), first_names, suffixes
# expected_stage: the stage we EXPECT to find it (informational)
# ---------------------------------------------------------------------------

GAUNTLET: list[tuple[str, str, dict, int | None]] = [
    # ── Trivially easy — Stage 1 (supplied full password) ──────────────────
    ("01 known_exact", "test", {"full_password": "test"}, 1),
    ("02 known_exact_digits", "123456", {"full_password": "123456"}, 1),
    ("03 known_exact_mixed", "Hello123!", {"full_password": "Hello123!"}, 1),
    # ── Top-10k common — Stage 4 ────────────────────────────────────────────
    ("04 top10k_password", "password", {}, 4),
    ("05 top10k_iloveyou", "iloveyou", {}, 4),
    ("06 top10k_admin", "admin", {}, 4),
    ("07 top10k_letmein", "letmein", {}, 4),
    ("08 top10k_123456789", "123456789", {}, 4),
    # ── RockYou — Stage 5 ───────────────────────────────────────────────────
    ("09 rockyou_monkey123", "monkey123", {}, 5),
    ("10 rockyou_sunshine", "sunshine", {}, 5),
    ("11 rockyou_dragon", "dragon", {}, 5),
    # ── Hint-driven wordlist — Stage 3 ──────────────────────────────────────
    ("12 hint_name_suffix", "isinho123", {"stems": ("isinho",)}, 3),
    ("13 hint_date_frag", "050196", {"dates": ((1, 5, 1996),)}, 3),
    ("14 hint_stem_dot", "satabola.", {"stems": ("satabola",)}, 3),
    ("15 hint_stem_year", "isinho1996", {"stems": ("isinho",), "dates": ((1, 5, 1996),)}, 3),
    ("16 hint_date_suffix", "0501961234", {"dates": ((1, 5, 1996),)}, 3),
    # The original ZIP from the session
    (
        "17 original_zip_pw",
        "0501961423",
        {"dates": ((1, 5, 1996),), "stems": ("isinho", "satabola")},
        3,
    ),
    # ── John Jumbo rules (mutations of common words) — Stage 6 ──────────────
    ("18 jumbo_P@ssword", "P@ssword", {}, 6),
    ("19 jumbo_Password1", "Password1", {}, 6),
    ("20 jumbo_Welcome1!", "Welcome1!", {}, 6),
    # ── Mask attack — Stage 8 ───────────────────────────────────────────────
    ("21 mask_upper_digits", "ABC12345", {"must_have": {"upper", "digit"}}, 8),
    ("22 mask_lower_digits", "qwerty99", {"must_have": {"lower", "digit"}}, 8),
    ("23 mask_cap_digits", "Summer23", {"must_have": {"upper", "lower", "digit"}}, 8),
    # ── Hybrid / PRINCE — Stages 9-10 ───────────────────────────────────────
    ("24 hybrid_word_mask", "dragon2025!", {}, 9),
    ("25 hybrid_cap_year", "Liverpool2024", {}, 9),
    # ── Brute force short — Stage 12 ────────────────────────────────────────
    ("26 bf_4chars", "xK9!", {"min_length": 4, "max_length": 4}, 12),
    ("27 bf_5chars", "aB3$e", {"min_length": 5, "max_length": 5}, 12),
    # ── Hard — random / long — expected to fail or take very long ────────────
    ("28 hard_random_8", "Xk9#mL2@", {}, None),
    ("29 hard_random_10", "zX2@kP8!mN", {}, None),
    ("30 hard_random_12", "rT5#uY8@vW1$", {}, None),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_zip(password: str, tmp_dir: Path) -> Path:
    """Create a small AES-256 encrypted ZIP with the given password."""
    safe = "".join(c if c.isalnum() else "_" for c in password[:20])
    path = tmp_dir / f"test_{safe}.zip"
    with pyzipper.AESZipFile(
        path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        encryption=pyzipper.WZ_AES,
    ) as zf:
        zf.setpassword(password.encode())
        zf.writestr("secret.txt", f"Password is: {password}\nThis is a test archive.")
    return path


def build_hints(hints_dict: dict):  # type: ignore[return]  # Hints imported lazily
    from uzpr.core.stages.protocol import Hints

    kw: dict = {}
    if "full_password" in hints_dict:
        kw["full_password"] = hints_dict["full_password"]
    if "stems" in hints_dict:
        kw["stems"] = tuple(hints_dict["stems"])
    if "dates" in hints_dict:
        kw["dates"] = tuple(hints_dict["dates"])
    if "first_names" in hints_dict:
        kw["first_names"] = tuple(hints_dict["first_names"])
    if "suffixes" in hints_dict:
        kw["suffixes"] = tuple(hints_dict["suffixes"])
    if "must_have" in hints_dict:
        kw["must_have"] = frozenset(hints_dict["must_have"])
    if "min_length" in hints_dict:
        kw["min_length"] = hints_dict["min_length"]
    if "max_length" in hints_dict:
        kw["max_length"] = hints_dict["max_length"]
    return Hints(**kw)


@dataclass
class Result:
    label: str
    password: str
    found: bool = False
    found_by_stage: int | None = None
    elapsed_s: float = 0.0
    error: str | None = None
    output: str = ""


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


async def run_one(
    label: str,
    archive: Path,
    hints_dict: dict,
    budget_s: float = 120.0,
    allowed_stages: list[int] | None = None,
) -> Result:
    from uzpr.app import build_application
    from uzpr.archive.detect import detect_archive
    from uzpr.core.stages.protocol import StageEvent, StageOutcome

    result = Result(label=label, password=hints_dict.get("full_password", "?"))
    events_log: list[str] = []

    async def on_event(e: StageEvent) -> None:
        if e.kind in ("log", "progress"):
            events_log.append(f"  stage={e.payload.get('stage_no', '?')} {e.kind}: {e.payload}")

    try:
        app_state = build_application()
        archive_info = detect_archive(archive)

        hints = build_hints(hints_dict)

        session_id = await app_state.repo.create_session(
            archive_info=archive_info,
            hints=hints,
            total_budget_s=budget_s,
            gpu_low_power=False,
        )

        t0 = time.perf_counter()
        stage_result = await app_state.orchestrator.run_session(session_id, on_event)
        result.elapsed_s = time.perf_counter() - t0

        if stage_result.outcome == StageOutcome.FOUND:
            result.found = True
            result.output = stage_result.password or ""
        else:
            result.found = False
            result.output = stage_result.outcome.value

    except Exception as exc:
        result.error = str(exc)
        result.elapsed_s = time.perf_counter() - t0 if "t0" in dir() else 0.0

    result.output = "\n".join(events_log[-5:]) if events_log else result.output
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main(
    stop_on_fail: bool, from_index: int, stages: list[int] | None, budget: float
) -> None:
    print("\n" + "=" * 70)
    print("  UZPR GAUNTLET TEST — 30 escalating passwords")
    print("=" * 70)

    tmp_dir = Path(tempfile.mkdtemp(prefix="uzpr_gauntlet_"))
    print(f"  Temp archives: {tmp_dir}\n")

    results: list[Result] = []
    passed = 0
    failed = 0

    for i, (label, password, hints_dict, expected_stage) in enumerate(GAUNTLET):
        if i + 1 < from_index:
            continue

        # Create archive
        archive = make_zip(password, tmp_dir)

        # Use per-test budget based on difficulty, unless --budget override given
        # Stages 1-3 (instant), 4-11 (seconds), 12+ (brute force = minutes)
        test_no = i + 1
        if budget != 60.0:
            test_budget = budget  # explicit override from CLI
        elif test_no <= 3:
            test_budget = 30.0  # known password — instant
        elif test_no <= 11:
            test_budget = 120.0  # dict / hint attacks
        elif test_no <= 20:
            test_budget = 180.0  # rules attacks
        elif test_no <= 25:
            test_budget = 300.0  # mask / hybrid — need more time
        elif test_no <= 27:
            test_budget = 600.0  # brute force 4-5 chars
        else:
            test_budget = 300.0  # hard random — expected fail

        print(
            f"[{label}]  pw={password!r:<22}  expected=stage{expected_stage or '??'}",
            end=" ",
            flush=True,
        )

        t0 = time.perf_counter()
        try:
            res = await asyncio.wait_for(
                run_one(label, archive, hints_dict, budget_s=test_budget, allowed_stages=stages),
                timeout=test_budget + 15,
            )
        except TimeoutError:
            res = Result(
                label=label, password=password, error="TIMEOUT", elapsed_s=test_budget + 15
            )

        elapsed = time.perf_counter() - t0

        if res.found:
            icon = "✅"
            passed += 1
        elif res.error:
            icon = "💥"
            failed += 1
        else:
            icon = "❌"
            failed += 1

        print(
            f"  {icon}  {elapsed:.1f}s  {'FOUND: ' + res.output if res.found else res.error or 'NOT FOUND (' + res.output + ')'}"
        )

        results.append(res)

        if (res.error or not res.found) and stop_on_fail and expected_stage is not None:
            print(f"\n⚠️  STOPPED: test {label} failed (--stop-on-fail active)")
            break

    # Summary
    print("\n" + "=" * 70)
    print(f"  RESULTS: {passed} passed, {failed} failed out of {len(results)} run")
    print("=" * 70)

    if failed:
        print("\nFAILED:")
        for r in results:
            if not r.found:
                print(
                    f"  {r.label:35s}  pw={r.password!r}  {'ERROR: ' + r.error if r.error else 'not found'}"
                )

    # Clean up temp dir
    import shutil

    shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UZPR gauntlet test")
    parser.add_argument(
        "--stop-on-fail", action="store_true", help="Stop on first unexpected failure"
    )
    parser.add_argument("--from", dest="from_index", type=int, default=1, help="Start from test N")
    parser.add_argument(
        "--stages", default=None, help="Comma-separated stage numbers to run (e.g. 1,3,4)"
    )
    parser.add_argument(
        "--budget", type=float, default=60.0, help="Per-test time budget in seconds (default 60)"
    )
    args = parser.parse_args()

    stages = [int(s) for s in args.stages.split(",")] if args.stages else None

    asyncio.run(
        main(
            stop_on_fail=args.stop_on_fail,
            from_index=args.from_index,
            stages=stages,
            budget=args.budget,
        )
    )
