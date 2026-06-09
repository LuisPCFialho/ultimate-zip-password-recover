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
from uzpr.engines.native import NativeVerifier
from uzpr.engines.tool_manager import ToolNotFoundError, find_tool
from uzpr.util.logging import get_logger
from uzpr.util.paths import install_dir

log = get_logger(__name__)

# Fallback list of 50 common passwords used when top10k.txt is not installed
_FALLBACK_PASSWORDS: tuple[str, ...] = (
    "123456",
    "password",
    "12345678",
    "qwerty",
    "123456789",
    "12345",
    "1234",
    "111111",
    "1234567",
    "dragon",
    "123123",
    "baseball",
    "iloveyou",
    "trustno1",
    "sunshine",
    "master",
    "welcome",
    "shadow",
    "ashley",
    "football",
    "jesus",
    "michael",
    "ninja",
    "mustang",
    "password1",
    "123",
    "abc123",
    "letmein",
    "monkey",
    "1234567890",
    "superman",
    "batman",
    "admin",
    "pass",
    "login",
    "hello",
    "charlie",
    "donald",
    "password123",
    "qwerty123",
    "princess",
    "solo",
    "passw0rd",
    "starwars",
    "whatever",
    "cheese",
    "computer",
    "liverpool",
    "hannah",
    "jessica",
)


def _locate_top10k(work_dir: Path) -> Path | None:
    # Try relative to work_dir (sessions/<id>/ → project root)
    candidate = work_dir.parent.parent.parent / "packaging" / "wordlists" / "top10k.txt"
    if candidate.is_file():
        return candidate
    # Try install dir
    try:
        install_candidate = install_dir() / "packaging" / "wordlists" / "top10k.txt"
        if install_candidate.is_file():
            return install_candidate
    except Exception:
        pass
    return None


class TopPasswordsStage:
    stage_no: int = 4
    name: str = "Top common passwords"
    engine: str = "hashcat"

    def __init__(self) -> None:
        self._stats = StageStats()
        self._active_runner: HashcatRunner | None = None

    async def prepare(self, ctx: StageContext) -> StagePlan:
        return StagePlan(
            estimated_keyspace=10000,
            estimated_candidates_per_sec=1_000_000.0,
            prior_probability=0.18,
            requires_gpu=True,
            can_resume=True,
        )

    async def run(self, ctx: StageContext, on_event: EventSink) -> StageResult:
        self._stats = StageStats()
        start = time.monotonic()

        outcome = StageOutcome.EXHAUSTED
        password: str | None = None

        top10k_path = _locate_top10k(ctx.work_dir)

        async def _body() -> None:
            nonlocal outcome, password

            try:
                binary = find_tool("hashcat")
                await _run_hashcat(binary, top10k_path)
            except ToolNotFoundError:
                log.warning(
                    "hashcat not available; falling back to native verifier for top passwords"
                )
                await _run_native(top10k_path)

        async def _run_hashcat(binary: Path, wordlist: Path | None) -> None:
            nonlocal outcome, password
            if ctx.hashcat_mode is None:
                log.warning("hashcat_mode is None; falling back to native")
                await _run_native(wordlist)
                return

            if wordlist is None:
                log.warning("top10k.txt not found; falling back to native with built-in list")
                await _run_native(None)
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

        async def _run_native(wordlist: Path | None) -> None:
            nonlocal outcome, password
            verifier = NativeVerifier(ctx.archive_path, ctx.archive_format)

            if wordlist is not None:
                candidates: list[str] = []
                with wordlist.open("r", encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        cand = line.rstrip("\r\n")
                        if cand:
                            candidates.append(cand)
            else:
                candidates = list(_FALLBACK_PASSWORDS)

            found = await verifier.verify_batch(candidates)
            self._stats.candidates_tested = len(candidates)
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
        if self._active_runner is not None:
            await self._active_runner.pause()
