from __future__ import annotations

import time
from pathlib import Path

import anyio

from uzpr.core.stages.protocol import (
    EventSink,
    Hints,
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
from uzpr.wordlist.generator import estimate_count, generate

log = get_logger(__name__)

_SKIPPED_PLAN = StagePlan(
    estimated_keyspace=0,
    estimated_candidates_per_sec=0.0,
    prior_probability=0.0,
    requires_gpu=False,
    can_resume=False,
)

_GPU_FORMATS = frozenset({"zip-aes", "rar3-hp", "rar5"})


def _has_hints(hints: Hints) -> bool:
    return bool(
        hints.stems
        or hints.dates
        or hints.first_names
        or hints.surnames
        or hints.nicknames
        or hints.pet_names
        or hints.places
    )


class SmartWordlistStage:
    stage_no: int = 3
    name: str = "Hint-driven smart wordlist"
    engine: str = "native"

    def __init__(self) -> None:
        self._stats = StageStats()
        self._active_runner: HashcatRunner | None = None

    async def prepare(self, ctx: StageContext) -> StagePlan:
        if not _has_hints(ctx.hints):
            return _SKIPPED_PLAN

        estimated_count = estimate_count(ctx.hints)
        return StagePlan(
            estimated_keyspace=estimated_count,
            estimated_candidates_per_sec=500_000.0,
            prior_probability=0.4,
            requires_gpu=False,
            can_resume=False,
        )

    async def run(self, ctx: StageContext, on_event: EventSink) -> StageResult:
        self._stats = StageStats()
        start = time.monotonic()

        if not _has_hints(ctx.hints):
            return StageResult(
                outcome=StageOutcome.SKIPPED,
                password=None,
                elapsed_seconds=0.0,
                stats=self._stats,
                restore_token=None,
            )

        outcome = StageOutcome.EXHAUSTED
        password: str | None = None

        async def _body() -> None:
            nonlocal outcome, password

            wordlist_path: Path = await generate(
                ctx.hints, ctx.work_dir, cap=10_000_000
            )

            if ctx.archive_format in _GPU_FORMATS:
                await _run_hashcat(wordlist_path)
            else:
                await _run_native(wordlist_path)

        async def _run_hashcat(wordlist_path: Path) -> None:
            nonlocal outcome, password
            if ctx.hashcat_mode is None:
                log.warning("hashcat_mode is None for GPU-preferred format; falling back to native")
                await _run_native(wordlist_path)
                return

            try:
                binary = find_tool("hashcat")
            except ToolNotFoundError:
                log.warning("hashcat not found, falling back to native verifier")
                await _run_native(wordlist_path)
                return

            runner = HashcatRunner(binary, ctx.work_dir)
            self._active_runner = runner
            result = await runner.run(
                ctx.hashcat_mode,
                0,  # attack mode: straight
                ctx.hash_file,
                str(wordlist_path),
                potfile=ctx.shared_potfile,
                session=ctx.stage_id,
                on_event=on_event,
            )
            self._active_runner = None
            self._stats = result.stats
            outcome = result.outcome
            password = result.password

        async def _run_native(wordlist_path: Path) -> None:
            nonlocal outcome, password
            verifier = NativeVerifier(ctx.archive_path, ctx.archive_format)
            batch: list[str] = []
            total_tested = 0

            with wordlist_path.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    candidate = line.rstrip("\r\n")
                    if not candidate:
                        continue
                    batch.append(candidate)

                    if len(batch) >= 1000:
                        found = await verifier.verify_batch(batch)
                        total_tested += len(batch)
                        self._stats.candidates_tested = total_tested
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

                        if total_tested % 5000 < 1000:
                            await on_event(
                                StageEvent(
                                    ts=time.time(),
                                    kind="progress",
                                    payload={"candidates_tested": total_tested},
                                )
                            )

            if batch:
                found = await verifier.verify_batch(batch)
                total_tested += len(batch)
                self._stats.candidates_tested = total_tested
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

        with anyio.move_on_after(ctx.budget_seconds):
            await _body()

        elapsed = time.monotonic() - start

        if outcome not in (StageOutcome.FOUND, StageOutcome.EXHAUSTED, StageOutcome.SKIPPED):
            await self.cancel()
            return StageResult(
                outcome=StageOutcome.ABORTED,
                password=None,
                elapsed_seconds=ctx.budget_seconds,
                stats=self._stats,
                restore_token=None,
            )

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
