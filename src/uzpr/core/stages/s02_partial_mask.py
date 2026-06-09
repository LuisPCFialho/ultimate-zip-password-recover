from __future__ import annotations

import itertools
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
from uzpr.engines.native import NativeVerifier
from uzpr.engines.tool_manager import ToolNotFoundError, find_tool
from uzpr.util.logging import get_logger

log = get_logger(__name__)

_CHARSET_SIZE = 95  # printable ASCII (?a)

_SKIPPED_PLAN = StagePlan(
    estimated_keyspace=0,
    estimated_candidates_per_sec=0.0,
    prior_probability=0.0,
    requires_gpu=False,
    can_resume=False,
)


def _count_unknowns(mask: str) -> int:
    return mask.count("?")


def _keyspace(mask: str) -> int:
    unknowns = _count_unknowns(mask)
    if unknowns == 0:
        return 1
    return _CHARSET_SIZE**unknowns


class PartialMaskStage:
    stage_no: int = 2
    name: str = "Partial mask completion"
    engine: str = "native"

    def __init__(self) -> None:
        self._stats = StageStats()
        self._active_runner: HashcatRunner | None = None

    async def prepare(self, ctx: StageContext) -> StagePlan:
        if ctx.hints.partial_mask is None:
            return _SKIPPED_PLAN

        keyspace = _keyspace(ctx.hints.partial_mask)
        large = keyspace > 50_000
        return StagePlan(
            estimated_keyspace=keyspace,
            estimated_candidates_per_sec=1_000_000.0 if large else 10_000.0,
            prior_probability=0.8,
            requires_gpu=large,
            can_resume=True,
        )

    async def run(self, ctx: StageContext, on_event: EventSink) -> StageResult:
        self._stats = StageStats()
        start = time.monotonic()

        if ctx.hints.partial_mask is None:
            return StageResult(
                outcome=StageOutcome.SKIPPED,
                password=None,
                elapsed_seconds=0.0,
                stats=self._stats,
                restore_token=None,
            )

        mask = ctx.hints.partial_mask
        keyspace = _keyspace(mask)
        outcome = StageOutcome.EXHAUSTED
        password: str | None = None
        aborted = False

        async def _body() -> None:
            nonlocal outcome, password, aborted

            if keyspace <= 50_000:
                await _run_native(mask, ctx, on_event)
            else:
                await _run_hashcat(mask, ctx, on_event)

        async def _run_native(mask: str, ctx: StageContext, on_event: EventSink) -> None:
            nonlocal outcome, password
            # Split mask into literal parts and placeholder positions
            prefix_parts: list[str] = []
            positions: list[int] = []
            for i, ch in enumerate(mask):
                if ch == "?":
                    positions.append(i)
            # Build charset
            charset = [chr(c) for c in range(32, 127)]  # printable ASCII

            verifier = NativeVerifier(ctx.archive_path, ctx.archive_format)
            batch: list[str] = []
            tested = 0

            for combo in itertools.product(charset, repeat=len(positions)):
                candidate_chars = list(mask)
                for idx, ch in zip(positions, combo):
                    candidate_chars[idx] = ch
                candidate = "".join(candidate_chars)
                batch.append(candidate)
                tested += 1

                if len(batch) >= 500:
                    found = await verifier.verify_batch(batch)
                    self._stats.candidates_tested += len(batch)
                    if found is not None:
                        outcome = StageOutcome.FOUND
                        password = found
                        await on_event(
                            StageEvent(
                                ts=time.time(),
                                kind="log",
                                payload={"msg": "Password found!"},
                            )
                        )
                        return
                    batch = []
                    await on_event(
                        StageEvent(
                            ts=time.time(),
                            kind="progress",
                            payload={"candidates_tested": self._stats.candidates_tested},
                        )
                    )

            if batch:
                found = await verifier.verify_batch(batch)
                self._stats.candidates_tested += len(batch)
                if found is not None:
                    outcome = StageOutcome.FOUND
                    password = found
                    await on_event(
                        StageEvent(
                            ts=time.time(),
                            kind="log",
                            payload={"msg": "Password found!"},
                        )
                    )

        async def _run_hashcat(mask: str, ctx: StageContext, on_event: EventSink) -> None:
            nonlocal outcome, password
            if ctx.hashcat_mode is None:
                log.warning("hashcat_mode is None, skipping hashcat run")
                outcome = StageOutcome.SKIPPED
                return

            try:
                binary = find_tool("hashcat")
            except ToolNotFoundError:
                log.warning("hashcat not found, falling back to native for large mask")
                await _run_native(mask, ctx, on_event)
                return

            mask_file: Path = ctx.work_dir / "stage2.mask"
            mask_file.write_text(mask, encoding="utf-8")

            runner = HashcatRunner(binary, ctx.work_dir)
            self._active_runner = runner
            result = await runner.run(
                ctx.hashcat_mode,
                3,  # attack mode: mask
                ctx.hash_file,
                str(mask_file),
                potfile=ctx.shared_potfile,
                session=ctx.stage_id,
                on_event=on_event,
            )
            self._active_runner = None
            self._stats = result.stats
            outcome = result.outcome
            password = result.password

        with anyio.move_on_after(ctx.budget_seconds):
            await _body()

        elapsed = time.monotonic() - start

        # If budget expired and we never reached a terminal outcome, it's aborted
        if outcome not in (StageOutcome.FOUND, StageOutcome.EXHAUSTED, StageOutcome.SKIPPED):
            await self.cancel()
            return StageResult(
                outcome=StageOutcome.ABORTED,
                password=None,
                elapsed_seconds=ctx.budget_seconds,
                stats=self._stats,
                restore_token=None,
            )

        # Detect budget expiry for long-running cases: if elapsed >= budget and not done
        if elapsed >= ctx.budget_seconds and outcome == StageOutcome.EXHAUSTED:
            await self.cancel()
            return StageResult(
                outcome=StageOutcome.ABORTED,
                password=None,
                elapsed_seconds=ctx.budget_seconds,
                stats=self._stats,
                restore_token=None,
            )

        return StageResult(
            outcome=outcome,
            password=password,
            elapsed_seconds=elapsed,
            stats=self._stats,
            restore_token=None,
        )

    async def cancel(self) -> None:
        if self._active_runner is not None:
            await self._active_runner.pause()
