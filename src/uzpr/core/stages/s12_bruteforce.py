from __future__ import annotations

import time

import anyio

from uzpr.core.stages.protocol import (
    EventSink,
    StageContext,
    StageEvent,
    StageOutcome,
    StagePlan,
    StageResult,
    StageStats,
)
from uzpr.engines.hashcat import HashcatRunner
from uzpr.engines.tool_manager import find_tool
from uzpr.util.logging import get_logger

log = get_logger(__name__)

# 95 printable ASCII characters (?a charset)
_CHARSET_SIZE = 95
# Default CPS when no capability probe data is available
_DEFAULT_CPS = 1_000_000.0
# Maximum length hashcat supports for incremental masks
_MAX_MASK_LEN = 16

_EMPTY_PLAN = StagePlan(
    estimated_keyspace=0,
    estimated_candidates_per_sec=_DEFAULT_CPS,
    prior_probability=0.0,
    requires_gpu=True,
    can_resume=True,
)


def _load_cached_cps(ctx: StageContext) -> float:
    """Read CPS from the capability_cache table for this mode, or return default."""
    if ctx.hashcat_mode is None:
        return _DEFAULT_CPS

    try:
        import json
        import sqlite3

        con = sqlite3.connect(str(ctx.tried_candidates_db), timeout=5)
        try:
            cur = con.execute(
                "SELECT benchmarks_json FROM capability_cache WHERE device_key LIKE ?",
                (f"%|{ctx.hashcat_mode}|%",),
            )
            row = cur.fetchone()
            if row:
                data: dict[str, object] = json.loads(row[0])
                for v in data.values():
                    if isinstance(v, (int, float)) and v > 0:
                        return float(v)
        finally:
            con.close()
    except Exception:
        pass

    return _DEFAULT_CPS


def _pick_max_length(
    min_len: int,
    max_len: int,
    cps: float,
    budget_seconds: float,
) -> int:
    """Return the largest length N where 95^N / cps <= budget_seconds."""
    chosen = min_len - 1
    for n in range(min_len, min(max_len, _MAX_MASK_LEN) + 1):
        ks = _CHARSET_SIZE ** n
        if ks / cps <= budget_seconds:
            chosen = n
        else:
            break
    return chosen


class BruteForceStage:
    stage_no: int = 12
    name: str = "Bounded brute force"
    engine: str = "hashcat"

    def __init__(self) -> None:
        self._stats = StageStats()
        self._active_runner: HashcatRunner | None = None

    async def prepare(self, ctx: StageContext) -> StagePlan:
        if ctx.hashcat_mode is None:
            return _EMPTY_PLAN

        cps = _load_cached_cps(ctx)
        hints = ctx.hints
        min_len = max(1, hints.min_length)
        max_len = min(hints.max_length, _MAX_MASK_LEN)

        chosen_max = _pick_max_length(min_len, max_len, cps, ctx.budget_seconds)
        if chosen_max < min_len:
            log.info(
                "bruteforce_no_length_fits_budget",
                min_len=min_len,
                max_len=max_len,
                budget=ctx.budget_seconds,
                cps=cps,
            )
            return _EMPTY_PLAN

        keyspace = sum(_CHARSET_SIZE ** n for n in range(min_len, chosen_max + 1))
        total_ks = sum(_CHARSET_SIZE ** n for n in range(min_len, max_len + 1))
        covered_ratio = keyspace / total_ks if total_ks > 0 else 1.0
        prior = min(0.5, covered_ratio)

        return StagePlan(
            estimated_keyspace=keyspace,
            estimated_candidates_per_sec=cps,
            prior_probability=prior,
            requires_gpu=True,
            can_resume=True,
        )

    async def run(self, ctx: StageContext, on_event: EventSink) -> StageResult:
        self._stats = StageStats()
        start = time.monotonic()

        if ctx.hashcat_mode is None:
            return StageResult(
                outcome=StageOutcome.SKIPPED,
                password=None,
                elapsed_seconds=0.0,
                stats=self._stats,
                restore_token=None,
            )

        cps = _load_cached_cps(ctx)
        hints = ctx.hints
        min_len = max(1, hints.min_length)
        max_len = min(hints.max_length, _MAX_MASK_LEN)

        chosen_max = _pick_max_length(min_len, max_len, cps, ctx.budget_seconds)
        if chosen_max < min_len:
            log.info("bruteforce_skipped_no_budget", min_len=min_len, max_len=max_len)
            return StageResult(
                outcome=StageOutcome.SKIPPED,
                password=None,
                elapsed_seconds=0.0,
                stats=self._stats,
                restore_token=None,
            )

        mask = "?a" * chosen_max
        extra_args = [
            mask,
            "--increment",
            f"--increment-min={min_len}",
            f"--increment-max={chosen_max}",
        ]

        binary = find_tool("hashcat")
        runner = HashcatRunner(binary, ctx.work_dir)
        self._active_runner = runner

        result: StageResult | None = None

        async def _body() -> None:
            nonlocal result
            result = await runner.run(
                ctx.hashcat_mode,  # type: ignore[arg-type]
                3,
                ctx.hash_file,
                *extra_args,
                potfile=ctx.shared_potfile,
                session=ctx.stage_id,
                on_event=on_event,
                low_power=ctx.low_power,
                gpu_devices=ctx.gpu_devices,
            )

        with anyio.move_on_after(ctx.budget_seconds):
            await _body()

        self._active_runner = None
        elapsed = time.monotonic() - start

        if result is None:
            await on_event(
                StageEvent(
                    ts=time.time(),
                    kind="log",
                    payload={"msg": "bruteforce budget exhausted, aborting"},
                )
            )
            return StageResult(
                outcome=StageOutcome.ABORTED,
                password=None,
                elapsed_seconds=elapsed,
                stats=self._stats,
                restore_token=ctx.stage_id,
            )

        self._stats = result.stats
        return StageResult(
            outcome=result.outcome,
            password=result.password,
            elapsed_seconds=elapsed,
            stats=self._stats,
            restore_token=result.restore_token,
            error=result.error,
        )

    async def cancel(self) -> None:
        runner = self._active_runner
        if runner is not None:
            await runner.pause()
