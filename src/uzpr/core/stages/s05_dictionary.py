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
from uzpr.engines.john import JohnRunner
from uzpr.engines.tool_manager import ToolNotFoundError, find_tool
from uzpr.util.logging import get_logger
from uzpr.util.paths import install_dir

log = get_logger(__name__)

_JOHN_FORMAT_MAP: dict[str, str] = {
    "zip-classic": "zip",
    "zip-aes": "zip-aes",
    "rar3-hp": "rar",
    "rar5": "rar5",
}


def _locate_wordlist(name: str, work_dir: Path) -> Path | None:
    # Try relative to work_dir (sessions/<id>/ → project root)
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


class DictionaryStage:
    stage_no: int = 5
    name: str = "Dictionary (rockyou + SecLists)"
    engine: str = "hashcat"

    def __init__(self) -> None:
        self._stats = StageStats()
        self._active_runner: HashcatRunner | JohnRunner | None = None

    async def prepare(self, ctx: StageContext) -> StagePlan:
        return StagePlan(
            estimated_keyspace=14_000_000,
            estimated_candidates_per_sec=2_000_000.0,
            prior_probability=0.20,
            requires_gpu=True,
            can_resume=True,
        )

    async def run(self, ctx: StageContext, on_event: EventSink) -> StageResult:
        self._stats = StageStats()
        start = time.monotonic()

        outcome = StageOutcome.EXHAUSTED
        password: str | None = None

        wordlist_path = (
            _locate_wordlist("rockyou.txt", ctx.work_dir)
            or _locate_wordlist("top100k.txt", ctx.work_dir)
            or _locate_wordlist("top10k.txt", ctx.work_dir)
        )

        if wordlist_path is None:
            log.warning("No wordlist found for DictionaryStage; returning SKIPPED")
            return StageResult(
                outcome=StageOutcome.SKIPPED,
                password=None,
                elapsed_seconds=0.0,
                stats=self._stats,
                restore_token=None,
            )

        async def _body() -> None:
            nonlocal outcome, password

            try:
                hashcat_bin = find_tool("hashcat")
                await _run_hashcat(hashcat_bin, wordlist_path)
                return
            except ToolNotFoundError:
                log.warning("hashcat not available; trying john for DictionaryStage")

            try:
                john_bin = find_tool("john")
                await _run_john(john_bin, wordlist_path)
            except ToolNotFoundError:
                log.warning("john not available; DictionaryStage cannot run")
                nonlocal outcome
                outcome = StageOutcome.FAILED

        async def _run_hashcat(binary: Path, wordlist: Path) -> None:
            nonlocal outcome, password
            if ctx.hashcat_mode is None:
                log.warning("hashcat_mode is None; skipping hashcat in DictionaryStage")
                return

            runner = HashcatRunner(binary, ctx.work_dir)
            self._active_runner = runner
            result = await runner.run(
                ctx.hashcat_mode,
                0,  # attack mode: straight
                ctx.hash_file,
                str(wordlist),
                potfile=ctx.shared_potfile,
                session=ctx.stage_id,
                on_event=on_event,
            )
            self._active_runner = None
            self._stats = result.stats
            outcome = result.outcome
            password = result.password

        async def _run_john(binary: Path, wordlist: Path) -> None:
            nonlocal outcome, password
            fmt = _JOHN_FORMAT_MAP.get(ctx.archive_format, "zip")
            runner = JohnRunner(binary, ctx.work_dir)
            self._active_runner = runner
            result = await runner.run(
                fmt,
                ctx.hash_file,
                f"--wordlist={wordlist}",
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
            StageOutcome.FAILED,
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
