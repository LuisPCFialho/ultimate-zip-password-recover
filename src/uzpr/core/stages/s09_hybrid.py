from __future__ import annotations

import time
from pathlib import Path

import anyio

from uzpr.core.stages.protocol import (
    EventSink,
    StageContext,
    StageOutcome,
    StagePlan,
    StageResult,
    StageStats,
)
from uzpr.engines.hashcat import HashcatRunner
from uzpr.engines.tool_manager import find_tool
from uzpr.util.logging import get_logger
from uzpr.util.paths import install_dir

log = get_logger(__name__)

_SMALL_MASKS = ["?d", "?d?d", "?d?d?d", "?d?d?d?d", "?s", "?s?d", "?d?s"]


def _find_wordlist(work_dir: Path) -> Path:
    """Return stage3.wordlist if present, else fall back to top10k.txt."""
    stage3 = work_dir / "stage3.wordlist"
    if stage3.is_file():
        return stage3

    # Search packaging/wordlists within the install tree
    candidates = [
        install_dir() / "packaging" / "wordlists" / "top10k.txt",
        install_dir() / "wordlists" / "top10k.txt",
    ]
    for path in candidates:
        if path.is_file():
            return path

    # Last resort: return the first candidate path (will fail at runtime with a
    # clear error from hashcat rather than silently doing nothing)
    return candidates[0]


class HybridStage:
    stage_no: int = 9
    name: str = "Hybrid dict+mask / mask+dict"
    engine: str = "hashcat"

    def __init__(self) -> None:
        self._stats = StageStats()
        self._active_runner: HashcatRunner | None = None

    async def prepare(self, ctx: StageContext) -> StagePlan:
        return StagePlan(
            estimated_keyspace=5_000_000,
            estimated_candidates_per_sec=3_000_000.0,
            prior_probability=0.08,
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

        wordlist = _find_wordlist(ctx.work_dir)
        binary = find_tool("hashcat")

        final_outcome = StageOutcome.EXHAUSTED
        final_password: str | None = None
        aborted = False

        async def _run_sub(attack: int, mask: str, sub_session: str) -> StageResult:
            runner = HashcatRunner(binary, ctx.work_dir)
            self._active_runner = runner

            if attack == 6:
                # dict + mask: hashcat -a 6 hash wordlist mask
                extra: list[str] = [str(wordlist), mask]
            else:
                # mask + dict: hashcat -a 7 hash mask wordlist
                extra = [mask, str(wordlist)]

            return await runner.run(
                ctx.hashcat_mode,  # type: ignore[arg-type]
                attack,
                ctx.hash_file,
                *extra,
                potfile=ctx.shared_potfile,
                session=sub_session,
                on_event=on_event,
                low_power=ctx.low_power,
                gpu_devices=ctx.gpu_devices,
            )

        async def _body() -> None:
            nonlocal final_outcome, final_password, aborted
            for i, mask in enumerate(_SMALL_MASKS):
                # dict + mask
                sub_a = f"{ctx.stage_id}_{i}_a6"
                res_a = await _run_sub(6, mask, sub_a)
                if res_a.outcome == StageOutcome.FOUND:
                    final_outcome = StageOutcome.FOUND
                    final_password = res_a.password
                    _accumulate_stats(self._stats, res_a.stats)
                    return
                if res_a.outcome == StageOutcome.FAILED:
                    log.warning("hybrid_sub_failed", session=sub_a, error=res_a.error)
                _accumulate_stats(self._stats, res_a.stats)

                # mask + dict
                sub_b = f"{ctx.stage_id}_{i}_a7"
                res_b = await _run_sub(7, mask, sub_b)
                if res_b.outcome == StageOutcome.FOUND:
                    final_outcome = StageOutcome.FOUND
                    final_password = res_b.password
                    _accumulate_stats(self._stats, res_b.stats)
                    return
                if res_b.outcome == StageOutcome.FAILED:
                    log.warning("hybrid_sub_failed", session=sub_b, error=res_b.error)
                _accumulate_stats(self._stats, res_b.stats)

        with anyio.move_on_after(ctx.budget_seconds):
            await _body()

        self._active_runner = None
        elapsed = time.monotonic() - start

        return StageResult(
            outcome=final_outcome,
            password=final_password,
            elapsed_seconds=elapsed,
            stats=self._stats,
            restore_token=None,
        )

    async def cancel(self) -> None:
        runner = self._active_runner
        if runner is not None:
            await runner.pause()


def _accumulate_stats(dst: StageStats, src: StageStats) -> None:
    """Merge per-sub-run stats into the aggregate stage stats."""
    dst.candidates_tested += src.candidates_tested
    dst.rejected_candidates += src.rejected_candidates
    if src.peak_candidates_per_sec > dst.peak_candidates_per_sec:
        dst.peak_candidates_per_sec = src.peak_candidates_per_sec
    if src.gpu_peak_temp_c is not None:
        if dst.gpu_peak_temp_c is None or src.gpu_peak_temp_c > dst.gpu_peak_temp_c:
            dst.gpu_peak_temp_c = src.gpu_peak_temp_c
