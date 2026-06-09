from __future__ import annotations

import time
from pathlib import Path

import anyio
import anyio.abc

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
from uzpr.engines.process_utils import open_managed_process, terminate_with_grace
from uzpr.engines.tool_manager import ToolNotFoundError, find_tool
from uzpr.util.logging import get_logger
from uzpr.util.paths import install_dir

log = get_logger(__name__)

_SKIPPED_PLAN = StagePlan(
    estimated_keyspace=0,
    estimated_candidates_per_sec=0.0,
    prior_probability=0.0,
    requires_gpu=True,
    can_resume=True,
)


def _find_top_dict(work_dir: Path) -> Path:
    """Return top10k.txt (or rockyou.txt) from the install tree."""
    candidates = [
        install_dir() / "packaging" / "wordlists" / "top10k.txt",
        install_dir() / "wordlists" / "top10k.txt",
        install_dir() / "packaging" / "wordlists" / "rockyou.txt",
        install_dir() / "wordlists" / "rockyou.txt",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


class PrinceStage:
    stage_no: int = 10
    name: str = "PRINCE"
    engine: str = "hashcat"

    def __init__(self) -> None:
        self._stats = StageStats()
        self._active_runner: HashcatRunner | None = None
        self._pp64_proc: anyio.abc.Process | None = None

    async def prepare(self, ctx: StageContext) -> StagePlan:
        hints = ctx.hints
        has_content = bool(hints.stems or hints.first_names or hints.nicknames or hints.pet_names)
        if not has_content:
            return _SKIPPED_PLAN

        return StagePlan(
            estimated_keyspace=10_000_000,
            estimated_candidates_per_sec=2_000_000.0,
            prior_probability=0.06,
            requires_gpu=True,
            can_resume=True,
        )

    async def run(self, ctx: StageContext, on_event: EventSink) -> StageResult:
        self._stats = StageStats()
        start = time.monotonic()

        hints = ctx.hints
        has_content = bool(hints.stems or hints.first_names or hints.nicknames or hints.pet_names)
        if not has_content:
            return StageResult(
                outcome=StageOutcome.SKIPPED,
                password=None,
                elapsed_seconds=0.0,
                stats=self._stats,
                restore_token=None,
            )

        if ctx.hashcat_mode is None:
            return StageResult(
                outcome=StageOutcome.SKIPPED,
                password=None,
                elapsed_seconds=0.0,
                stats=self._stats,
                restore_token=None,
            )

        # Build stems list
        stems: list[str] = (
            list(hints.stems)
            + list(hints.first_names)
            + list(hints.nicknames)
            + list(hints.pet_names)
        )

        top_dict_path = _find_top_dict(ctx.work_dir)
        elements_path = ctx.work_dir / "elements.txt"

        try:
            from uzpr.wordlist.prince import build_prince_elements  # type: ignore[import-untyped]

            build_prince_elements(stems, top_dict_path, elements_path)
        except Exception as exc:
            log.warning("prince_build_elements_failed", error=str(exc))
            # Fall back: write stems directly as elements
            elements_path.write_text("\n".join(stems) + "\n", encoding="utf-8")

        try:
            pp64_binary = find_tool("pp64")
        except ToolNotFoundError:
            log.warning("prince_pp64_not_found")
            return StageResult(
                outcome=StageOutcome.SKIPPED,
                password=None,
                elapsed_seconds=time.monotonic() - start,
                stats=self._stats,
                restore_token=None,
            )

        hashcat_binary = find_tool("hashcat")

        result: StageResult | None = None

        async def _body() -> None:
            nonlocal result
            result = await _run_prince_pipeline(
                ctx=ctx,
                pp64_binary=pp64_binary,
                hashcat_binary=hashcat_binary,
                elements_path=elements_path,
                on_event=on_event,
                stage=self,
            )

        with anyio.move_on_after(ctx.budget_seconds):
            await _body()

        self._active_runner = None
        self._pp64_proc = None
        elapsed = time.monotonic() - start

        if result is None:
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
        pp64 = self._pp64_proc
        if pp64 is not None:
            await terminate_with_grace(pp64, sigterm_after_s=5.0, sigkill_after_s=10.0)
            self._pp64_proc = None

        runner = self._active_runner
        if runner is not None:
            await runner.pause()
            self._active_runner = None


async def _run_prince_pipeline(
    *,
    ctx: StageContext,
    pp64_binary: Path,
    hashcat_binary: Path,
    elements_path: Path,
    on_event: EventSink,
    stage: PrinceStage,
) -> StageResult:
    """Run pp64 piped into hashcat -a 0 - and return the StageResult."""
    import json
    import time as _time

    from uzpr.core.stages.protocol import StageOutcome, StageResult, StageStats

    # Launch pp64 reading from elements.txt
    pp64_argv = [str(pp64_binary)]
    pp64_proc = await open_managed_process(
        pp64_argv,
        cwd=ctx.work_dir,
        stdin=anyio.abc.ByteStream,  # type: ignore[arg-type]
        stdout=anyio.abc.ByteStream,  # type: ignore[arg-type]
        stderr=None,
    )
    stage._pp64_proc = pp64_proc

    # hashcat -a 0 reading candidates from stdin (-)
    session = ctx.stage_id
    work_dir = ctx.work_dir
    hc_argv = [
        str(hashcat_binary),
        "-m",
        str(ctx.hashcat_mode),
        "-a",
        "0",
        str(ctx.hash_file),
        "-",  # read candidates from stdin
        "--quiet",
        "--status",
        "--status-json",
        "--status-timer=2",
        f"--session={session}",
        f"--restore-file-path={work_dir / (session + '.restore')}",
        f"--potfile-path={ctx.shared_potfile}",
        f"--outfile={work_dir / (session + '.out')}",
        "--outfile-format=2",
        "-O",
    ]
    if ctx.low_power:
        hc_argv += ["-w", "1", "--hwmon-temp-abort=75"]
    else:
        hc_argv += ["-w", "2"]
    if ctx.gpu_devices:
        hc_argv += ["-d", ",".join(str(d) for d in ctx.gpu_devices)]

    hc_proc = await open_managed_process(
        hc_argv,
        cwd=work_dir,
        stdin=anyio.abc.ByteStream,  # type: ignore[arg-type]
        stdout=anyio.abc.ByteStream,  # type: ignore[arg-type]
        stderr=None,
    )

    stats = StageStats()
    run_start = _time.time()

    async def _feed_hashcat() -> None:
        """Stream pp64 stdout into hashcat stdin, then send EOF."""
        assert pp64_proc.stdin is not None
        assert hc_proc.stdin is not None

        # Send elements file contents to pp64 stdin, then close
        try:
            data = elements_path.read_bytes()
            await pp64_proc.stdin.send(data)
        finally:
            await pp64_proc.stdin.aclose()

        # Relay pp64 stdout → hashcat stdin
        assert pp64_proc.stdout is not None
        try:
            async for chunk in pp64_proc.stdout:
                await hc_proc.stdin.send(chunk)
        finally:
            await hc_proc.stdin.aclose()

    async def _read_hashcat_stdout() -> None:
        assert hc_proc.stdout is not None
        buf = b""
        async for chunk in hc_proc.stdout:
            buf += chunk
            while b"\n" in buf:
                line_bytes, buf = buf.split(b"\n", 1)
                line = line_bytes.decode(errors="replace").strip()
                if not line:
                    continue
                try:
                    data: dict[str, object] = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue

                progress = data.get("progress")
                if isinstance(progress, list) and len(progress) >= 1:
                    tested = progress[0]
                    if isinstance(tested, int):
                        stats.candidates_tested = tested

                speed = data.get("speed")
                if isinstance(speed, list):
                    total: float = sum(float(s) for s in speed if isinstance(s, (int, float)))
                    if total > stats.peak_candidates_per_sec:
                        stats.peak_candidates_per_sec = total

                await on_event(
                    StageEvent(
                        ts=_time.time(),
                        kind="progress",
                        payload={"raw": data},
                    )
                )

    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(_feed_hashcat)
            tg.start_soon(_read_hashcat_stdout)
    except Exception as exc:
        log.warning("prince_pipeline_error", error=str(exc))
    finally:
        await pp64_proc.wait()
        await hc_proc.wait()

    elapsed = _time.time() - run_start
    rc = hc_proc.returncode
    out_file = work_dir / f"{session}.out"

    password: str | None = None
    if out_file.is_file():
        for raw_line in out_file.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = raw_line.strip()
            if stripped:
                password = stripped
                break

    if password is not None:
        return StageResult(
            outcome=StageOutcome.FOUND,
            password=password,
            elapsed_seconds=elapsed,
            stats=stats,
            restore_token=session,
        )

    if rc == 0 or rc == 1:  # 1 = exhausted in hashcat
        return StageResult(
            outcome=StageOutcome.EXHAUSTED,
            password=None,
            elapsed_seconds=elapsed,
            stats=stats,
            restore_token=session,
        )

    return StageResult(
        outcome=StageOutcome.FAILED,
        password=None,
        elapsed_seconds=elapsed,
        stats=stats,
        restore_token=session,
        error=f"hashcat exited with code {rc}",
    )
