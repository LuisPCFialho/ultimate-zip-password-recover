from __future__ import annotations

import itertools
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
from uzpr.engines.john import JohnRunner
from uzpr.engines.tool_manager import ToolNotFoundError, find_tool
from uzpr.util.logging import get_logger
from uzpr.util.paths import install_dir

log = get_logger(__name__)

_SKIPPED_PLAN = StagePlan(
    estimated_keyspace=0,
    estimated_candidates_per_sec=0.0,
    prior_probability=0.0,
    requires_gpu=False,
    can_resume=False,
)

_JOHN_FORMAT_MAP: dict[str, str] = {
    "zip-classic": "pkzip",
    "zip-aes": "zip-aes",
    "rar3-hp": "rar",
    "rar5": "rar5",
}

_ROCKYOU_HEAD_LINES = 100_000


def _locate_wordlist(name: str, work_dir: Path) -> Path | None:
    candidate = work_dir.parent.parent.parent / "packaging" / "wordlists" / name
    if candidate.is_file():
        return candidate
    try:
        install_candidate = install_dir() / "packaging" / "wordlists" / name
        if install_candidate.is_file():
            return install_candidate
    except Exception:
        pass
    return None


def _build_combined_wordlist(
    stage3_wordlist: Path | None,
    rockyou_path: Path | None,
    out_path: Path,
) -> None:
    """Write combined wordlist to out_path from available sources."""
    with out_path.open("w", encoding="utf-8", errors="replace") as fout:
        # Write stage3 wordlist lines first
        if stage3_wordlist is not None and stage3_wordlist.is_file():
            with stage3_wordlist.open("r", encoding="utf-8", errors="replace") as fin:
                for line in fin:
                    fout.write(line)

        # Append first _ROCKYOU_HEAD_LINES lines of rockyou
        if rockyou_path is not None and rockyou_path.is_file():
            with rockyou_path.open("r", encoding="utf-8", errors="replace") as fin:
                for line in itertools.islice(fin, _ROCKYOU_HEAD_LINES):
                    fout.write(line)


class JohnRulesStage:
    stage_no: int = 6
    name: str = "john Jumbo rules"
    engine: str = "john"

    def __init__(self) -> None:
        self._stats = StageStats()
        self._active_runner: JohnRunner | None = None

    async def prepare(self, ctx: StageContext) -> StagePlan:
        try:
            find_tool("john")
        except ToolNotFoundError:
            log.info("john binary not found; JohnRulesStage will be skipped")
            return _SKIPPED_PLAN

        return StagePlan(
            estimated_keyspace=100_000,
            estimated_candidates_per_sec=500_000.0,
            prior_probability=0.12,
            requires_gpu=False,
            can_resume=True,
        )

    async def run(self, ctx: StageContext, on_event: EventSink) -> StageResult:
        self._stats = StageStats()
        start = time.monotonic()

        try:
            john_bin = find_tool("john")
        except ToolNotFoundError:
            log.info("john not found at run time; skipping JohnRulesStage")
            return StageResult(
                outcome=StageOutcome.SKIPPED,
                password=None,
                elapsed_seconds=0.0,
                stats=self._stats,
                restore_token=None,
            )

        stage3_wordlist = ctx.work_dir / "stage3.wordlist"
        rockyou_path = _locate_wordlist("rockyou.txt", ctx.work_dir)

        combined_wordlist = ctx.work_dir / "stage6.wordlist"
        _build_combined_wordlist(
            stage3_wordlist if stage3_wordlist.is_file() else None,
            rockyou_path,
            combined_wordlist,
        )

        if not combined_wordlist.is_file() or combined_wordlist.stat().st_size == 0:
            log.warning("No usable wordlist for JohnRulesStage; skipping")
            return StageResult(
                outcome=StageOutcome.SKIPPED,
                password=None,
                elapsed_seconds=0.0,
                stats=self._stats,
                restore_token=None,
            )

        fmt = _JOHN_FORMAT_MAP.get(ctx.archive_format, "zip")
        outcome = StageOutcome.EXHAUSTED
        password: str | None = None

        async def _body() -> None:
            nonlocal outcome, password
            runner = JohnRunner(john_bin, ctx.work_dir)
            self._active_runner = runner
            result = await runner.run(
                fmt,
                ctx.hash_file,
                "--rules=jumbo",
                f"--wordlist={combined_wordlist}",
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

        if outcome not in (
            StageOutcome.FOUND,
            StageOutcome.EXHAUSTED,
            StageOutcome.SKIPPED,
        ):
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
