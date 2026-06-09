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

_RULE_PACKS: tuple[str, ...] = (
    "OneRuleToRuleThemAll.rule",
    "best64.rule",
    "dive.rule",
)


def _locate_rule(name: str, work_dir: Path) -> Path | None:
    candidate = work_dir.parent.parent.parent / "packaging" / "rules" / name
    if candidate.is_file():
        return candidate
    try:
        install_candidate = install_dir() / "packaging" / "rules" / name
        if install_candidate.is_file():
            return install_candidate
    except Exception:
        pass
    return None


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


class HashcatRulesStage:
    stage_no: int = 7
    name: str = "hashcat rule packs"
    engine: str = "hashcat"

    def __init__(self) -> None:
        self._stats = StageStats()
        self._active_runner: HashcatRunner | None = None

    async def prepare(self, ctx: StageContext) -> StagePlan:
        try:
            find_tool("hashcat")
        except ToolNotFoundError:
            log.info("hashcat binary not found; HashcatRulesStage will be skipped")
            return _SKIPPED_PLAN

        return StagePlan(
            estimated_keyspace=50_000_000,
            estimated_candidates_per_sec=5_000_000.0,
            prior_probability=0.15,
            requires_gpu=True,
            can_resume=True,
        )

    async def run(self, ctx: StageContext, on_event: EventSink) -> StageResult:
        self._stats = StageStats()
        start = time.monotonic()

        try:
            hashcat_bin = find_tool("hashcat")
        except ToolNotFoundError:
            log.info("hashcat not found at run time; skipping HashcatRulesStage")
            return StageResult(
                outcome=StageOutcome.SKIPPED,
                password=None,
                elapsed_seconds=0.0,
                stats=self._stats,
                restore_token=None,
            )

        if ctx.hashcat_mode is None:
            log.warning("hashcat_mode is None; skipping HashcatRulesStage")
            return StageResult(
                outcome=StageOutcome.SKIPPED,
                password=None,
                elapsed_seconds=0.0,
                stats=self._stats,
                restore_token=None,
            )

        # Choose wordlist: prefer stage3.wordlist, fall back to top10k.txt
        stage3_wordlist = ctx.work_dir / "stage3.wordlist"
        if stage3_wordlist.is_file():
            base_wordlist: Path = stage3_wordlist
        else:
            fallback = _locate_wordlist("top10k.txt", ctx.work_dir)
            if fallback is None:
                log.warning("No wordlist found for HashcatRulesStage; skipping")
                return StageResult(
                    outcome=StageOutcome.SKIPPED,
                    password=None,
                    elapsed_seconds=0.0,
                    stats=self._stats,
                    restore_token=None,
                )
            base_wordlist = fallback

        outcome = StageOutcome.EXHAUSTED
        password: str | None = None

        async def _body() -> None:
            nonlocal outcome, password

            for rule_name in _RULE_PACKS:
                rule_path = _locate_rule(rule_name, ctx.work_dir)
                if rule_path is None:
                    log.info("Rule pack %s not found; skipping this pack", rule_name)
                    continue

                runner = HashcatRunner(hashcat_bin, ctx.work_dir)
                self._active_runner = runner
                result = await runner.run(
                    ctx.hashcat_mode,  # type: ignore[arg-type]
                    0,  # attack mode: straight
                    ctx.hash_file,
                    "-r",
                    str(rule_path),
                    str(base_wordlist),
                    potfile=ctx.shared_potfile,
                    session=f"{ctx.stage_id}_{rule_name}",
                    on_event=on_event,
                )
                self._active_runner = None
                self._stats.candidates_tested += result.stats.candidates_tested
                if result.stats.peak_candidates_per_sec > self._stats.peak_candidates_per_sec:
                    self._stats.peak_candidates_per_sec = result.stats.peak_candidates_per_sec

                if result.outcome == StageOutcome.FOUND:
                    outcome = StageOutcome.FOUND
                    password = result.password
                    return

                # Pack exhausted — log and continue to the next
                await on_event(
                    StageEvent(
                        ts=time.time(),
                        kind="log",
                        payload={"msg": f"Rule pack {rule_name} exhausted, trying next"},
                    )
                )

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
