from __future__ import annotations

import time
from pathlib import Path

import anyio

from uzpr.core.stages.protocol import (
    EventSink,
    StagePlan,
    StageContext,
    StageEvent,
    StageOutcome,
    StageResult,
    StageStats,
)
from uzpr.engines.hashcat import HashcatRunner
from uzpr.engines.tool_manager import find_tool
from uzpr.util.logging import get_logger
from uzpr.util.paths import install_dir

log = get_logger(__name__)

# Maximum mask length hashcat will accept for incremental brute-force
_MAX_MASK_LEN = 16


def _find_hcstat2() -> Path | None:
    """Locate an hcstat2 file bundled with UZPR or hashcat's own default."""
    candidates = [
        install_dir() / "packaging" / "hcstat2" / "uzpr.hcstat2",
        install_dir() / "tools" / "hashcat" / "hashcat.hcstat2",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


class MarkovStage:
    stage_no: int = 11
    name: str = "Markov / hcstat2"
    engine: str = "hashcat"

    def __init__(self) -> None:
        self._stats = StageStats()
        self._active_runner: HashcatRunner | None = None

    async def prepare(self, ctx: StageContext) -> StagePlan:
        return StagePlan(
            estimated_keyspace=50_000_000,
            estimated_candidates_per_sec=5_000_000.0,
            prior_probability=0.05,
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

        hints = ctx.hints
        min_len = max(1, hints.min_length)
        max_len = min(hints.max_length, _MAX_MASK_LEN) if hints.max_length else 8

        # Build a mask of ?a characters sized to max_len (hashcat truncates to
        # --increment-max automatically)
        mask = "?a" * max_len

        hcstat2_path = _find_hcstat2()

        extra_args: list[str] = [
            mask,
            "--markov-threshold=0",
            "--increment",
            f"--increment-min={min_len}",
            f"--increment-max={max_len}",
        ]
        if hcstat2_path is not None:
            extra_args.append(f"--markov-hcstat2={hcstat2_path}")
            log.debug("markov_hcstat2", path=str(hcstat2_path))
        else:
            log.debug("markov_hcstat2_not_found_using_builtin")

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
                    payload={"msg": "markov stage budget exhausted, aborting"},
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
