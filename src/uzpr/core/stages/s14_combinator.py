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
from uzpr.engines.tool_manager import ToolNotFoundError, find_tool
from uzpr.util.logging import get_logger
from uzpr.util.paths import install_dir

log = get_logger(__name__)

# Keep lists small — keyspace is multiplicative (|L| * |R|).
_LEFT_MAX = 1000
_RIGHT_TAILS: tuple[str, ...] = (
    "!",
    "123",
    "1",
    "01",
    "2025",
    "2024",
    "2023",
    "2022",
    "2021",
    "2020",
    "2019",
    "2018",
)


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


def _read_top_n(path: Path, n: int) -> list[str]:
    out: list[str] = []
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            w = line.rstrip("\r\n")
            if w:
                out.append(w)
            if len(out) >= n:
                break
    return out


def _build_lists(ctx: StageContext) -> tuple[Path, Path] | None:
    """Materialize left.txt and right.txt in the work dir. Returns paths or None."""
    work = ctx.work_dir
    left_path = work / "combinator_left.txt"
    right_path = work / "combinator_right.txt"

    is_pt = ctx.hints.locale.startswith("pt")

    left_words: list[str] = []
    right_words: list[str] = []

    if is_pt:
        for name in ("pt-PT/pt_palavras.txt", "pt-PT/pt_nomes.txt"):
            located = _locate_wordlist(name, work)
            if located is not None:
                left_words.extend(_read_top_n(located, _LEFT_MAX))
        anos = _locate_wordlist("pt-PT/pt_anos.txt", work)
        if anos is not None:
            right_words.extend(_read_top_n(anos, 200))

    # Always seed from top10k as a baseline.
    top10k = _locate_wordlist("top10k.txt", work)
    if top10k is not None:
        baseline = _read_top_n(top10k, _LEFT_MAX)
        if not left_words:
            left_words = list(baseline)
        if not right_words:
            right_words = list(baseline)

    if not left_words or not right_words:
        return None

    # Trim to keyspace bound and deduplicate while preserving order.
    def _dedup(seq: list[str], cap: int) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for w in seq:
            if w in seen:
                continue
            seen.add(w)
            out.append(w)
            if len(out) >= cap:
                break
        return out

    left_words = _dedup(left_words, _LEFT_MAX)
    right_words = _dedup([*right_words, *_RIGHT_TAILS], _LEFT_MAX)

    left_path.write_text("\n".join(left_words) + "\n", encoding="utf-8")
    right_path.write_text("\n".join(right_words) + "\n", encoding="utf-8")
    return left_path, right_path


class CombinatorStage:
    stage_no: int = 14
    name: str = "Combinator (-a 1)"
    engine: str = "hashcat"

    def __init__(self) -> None:
        self._stats = StageStats()
        self._active_runner: HashcatRunner | None = None

    async def prepare(self, ctx: StageContext) -> StagePlan:
        prior = 0.08 if ctx.hashcat_mode is not None else 0.0
        return StagePlan(
            estimated_keyspace=_LEFT_MAX * _LEFT_MAX,
            estimated_candidates_per_sec=2_000_000.0,
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

        try:
            hashcat_bin = find_tool("hashcat")
        except ToolNotFoundError:
            log.warning("hashcat not available; CombinatorStage skipped")
            return StageResult(
                outcome=StageOutcome.SKIPPED,
                password=None,
                elapsed_seconds=0.0,
                stats=self._stats,
                restore_token=None,
            )

        lists = _build_lists(ctx)
        if lists is None:
            log.warning("CombinatorStage: missing source wordlists; skipping")
            return StageResult(
                outcome=StageOutcome.SKIPPED,
                password=None,
                elapsed_seconds=0.0,
                stats=self._stats,
                restore_token=None,
            )

        left_path, right_path = lists
        outcome = StageOutcome.EXHAUSTED
        password: str | None = None

        async def _body() -> None:
            nonlocal outcome, password
            runner = HashcatRunner(hashcat_bin, ctx.work_dir)
            self._active_runner = runner
            result = await runner.run(
                ctx.hashcat_mode,  # type: ignore[arg-type]
                1,  # attack mode: combinator
                ctx.hash_file,
                str(left_path),
                str(right_path),
                potfile=ctx.shared_potfile,
                session=f"{ctx.stage_id}_combinator",
                on_event=on_event,
                low_power=ctx.low_power,
                gpu_devices=ctx.gpu_devices,
            )
            self._active_runner = None
            self._stats.candidates_tested += result.stats.candidates_tested
            self._stats.rejected_candidates += result.stats.rejected_candidates
            if result.stats.peak_candidates_per_sec > self._stats.peak_candidates_per_sec:
                self._stats.peak_candidates_per_sec = result.stats.peak_candidates_per_sec
            outcome = result.outcome
            password = result.password

        with anyio.move_on_after(ctx.budget_seconds):
            await _body()

        elapsed = time.monotonic() - start

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
