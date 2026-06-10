from __future__ import annotations

import time
from pathlib import Path

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

# Wordlists in prevalence order (most-common-first). Each ships already sorted
# by real-world frequency, so they are NEVER re-sorted here. We run them as
# separate hashcat -a 0 passes, cheapest-first, stopping on the first FOUND.
_WORDLISTS: tuple[str, ...] = (
    "top10k.txt",
    "top100k.txt",
    "rockyou.txt",
    # HIBP prevalence oracle: deeper fallback after rockyou exhausts.
    "hibp_top1m.txt",
)

# pt-PT locale pack — inserted between top100k.txt and rockyou.txt when the
# user's locale starts with "pt". Hand-curated and small, so they're cheap.
_PT_PT_WORDLISTS: tuple[str, ...] = (
    "pt-PT/pt_palavras.txt",
    "pt-PT/pt_clubes.txt",
    "pt-PT/pt_nomes.txt",
    "pt-PT/pt_cidades.txt",
)


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


def _ordered_wordlist_names(locale: str) -> tuple[str, ...]:
    # Insert the pt-PT pack between top100k and rockyou for pt-* locales.
    if locale.startswith("pt"):
        return ("top10k.txt", "top100k.txt", *_PT_PT_WORDLISTS, "rockyou.txt")
    return _WORDLISTS


class DictionaryStage:
    stage_no: int = 5
    name: str = "Dictionary (rockyou + SecLists)"
    engine: str = "hashcat"

    def __init__(self) -> None:
        self._stats = StageStats()
        self._active_runner: HashcatRunner | JohnRunner | None = None

    def _accumulate(self, stats: StageStats) -> None:
        self._stats.candidates_tested += stats.candidates_tested
        self._stats.rejected_candidates += stats.rejected_candidates
        if stats.peak_candidates_per_sec > self._stats.peak_candidates_per_sec:
            self._stats.peak_candidates_per_sec = stats.peak_candidates_per_sec

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

        # Resolve wordlists in prevalence order, keeping only those that exist.
        wordlists: list[tuple[str, Path]] = []
        for name in _ordered_wordlist_names(ctx.hints.locale):
            located = _locate_wordlist(name, ctx.work_dir)
            if located is not None:
                wordlists.append((name, located))

        if not wordlists:
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
                runner_kind = "hashcat"
            except ToolNotFoundError:
                log.warning("hashcat not available; trying john for DictionaryStage")
                try:
                    hashcat_bin = None
                    john_bin = find_tool("john")
                    runner_kind = "john"
                except ToolNotFoundError:
                    log.warning("john not available; DictionaryStage cannot run")
                    outcome = StageOutcome.FAILED
                    return

            if runner_kind == "hashcat" and ctx.hashcat_mode is None:
                log.warning("hashcat_mode is None; skipping hashcat in DictionaryStage")
                outcome = StageOutcome.SKIPPED
                return

            # Iterate wordlists cheapest-first, each as a separate run, stopping
            # on the first FOUND. Wordlists are already in prevalence order; we
            # never re-sort them.
            for name, wordlist in wordlists:
                await on_event(
                    StageEvent(
                        ts=time.time(),
                        kind="log",
                        payload={"msg": f"Dictionary: trying wordlist {name}"},
                    )
                )

                if runner_kind == "hashcat":
                    assert hashcat_bin is not None
                    await _run_hashcat(hashcat_bin, name, wordlist)
                else:
                    await _run_john(john_bin, name, wordlist)

                if outcome == StageOutcome.FOUND:
                    return

        async def _run_hashcat(binary: Path, name: str, wordlist: Path) -> None:
            nonlocal outcome, password
            assert ctx.hashcat_mode is not None
            runner = HashcatRunner(binary, ctx.work_dir)
            self._active_runner = runner
            result = await runner.run(
                ctx.hashcat_mode,
                0,  # attack mode: straight
                ctx.hash_file,
                str(wordlist),
                potfile=ctx.shared_potfile,
                session=f"{ctx.stage_id}_{name}",
                on_event=on_event,
            )
            self._active_runner = None
            self._accumulate(result.stats)
            outcome = result.outcome
            password = result.password

        async def _run_john(binary: Path, name: str, wordlist: Path) -> None:
            nonlocal outcome, password
            fmt = _JOHN_FORMAT_MAP.get(ctx.archive_format, "zip")
            runner = JohnRunner(binary, ctx.work_dir)
            self._active_runner = runner
            result = await runner.run(
                fmt,
                ctx.hash_file,
                f"--wordlist={wordlist}",
                potfile=ctx.shared_potfile,
                session=f"{ctx.stage_id}_{name}",
                on_event=on_event,
            )
            self._active_runner = None
            self._accumulate(result.stats)
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
