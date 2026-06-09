from __future__ import annotations

import time

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
from uzpr.engines.native import NativeVerifier
from uzpr.util.logging import get_logger

log = get_logger(__name__)

_SKIPPED_PLAN = StagePlan(
    estimated_keyspace=0,
    estimated_candidates_per_sec=0.0,
    prior_probability=0.0,
    requires_gpu=False,
    can_resume=False,
)


class KnownPasswordStage:
    stage_no: int = 1
    name: str = "Known password verify"
    engine: str = "native"

    def __init__(self) -> None:
        self._stats = StageStats()
        self._active_runner: None = None  # no external runner for this stage

    async def prepare(self, ctx: StageContext) -> StagePlan:
        if ctx.hints.full_password is None:
            return _SKIPPED_PLAN
        return StagePlan(
            estimated_keyspace=1,
            estimated_candidates_per_sec=1.0,
            prior_probability=1.0,
            requires_gpu=False,
            can_resume=False,
        )

    async def run(self, ctx: StageContext, on_event: EventSink) -> StageResult:
        self._stats = StageStats()
        start = time.monotonic()

        if ctx.hints.full_password is None:
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
            verifier = NativeVerifier(ctx.archive_path, ctx.archive_format)
            found = await verifier.verify(ctx.hints.full_password)  # type: ignore[arg-type]
            self._stats.candidates_tested = 1
            if found:
                password = ctx.hints.full_password
                outcome = StageOutcome.FOUND
                await on_event(
                    StageEvent(
                        ts=time.time(),
                        kind="log",
                        payload={"msg": "Password found!"},
                    )
                )
            else:
                outcome = StageOutcome.EXHAUSTED

        with anyio.move_on_after(ctx.budget_seconds):
            await _body()

        elapsed = time.monotonic() - start

        if outcome not in (StageOutcome.FOUND, StageOutcome.EXHAUSTED):
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
        pass  # no external runner to pause
