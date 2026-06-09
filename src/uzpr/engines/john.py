from __future__ import annotations

import re
import time
from pathlib import Path

import anyio
import anyio.abc

from uzpr.core.stages.protocol import (
    EventSink,
    StageEvent,
    StageOutcome,
    StageResult,
    StageStats,
)
from uzpr.engines.process_utils import (
    open_managed_process,
    send_ctrl_break,
)
from uzpr.util.logging import get_logger

log = get_logger(__name__)

# Regex matching john's stderr progress line, e.g.:
#   1g 0:00:00:02 DONE (2024-01-01 12:00) 45.67%  3 passwords cracked
#   0g 0:00:00:01 0.00% (ETA: ...) 12345p/s
_PROGRESS_RE = re.compile(r"(\d+)g\s+\S+\s+([0-9.]+)%.*?(\d+)p/s")

_POLL_INTERVAL_S = 3.0


class JohnRunner:
    """Wraps the John the Ripper binary for cracking."""

    def __init__(self, binary: Path, work_dir: Path) -> None:
        self._binary = binary
        # john/run directory is the cwd for all john invocations
        self._john_run_dir = binary.parent
        self._work_dir = work_dir
        self._proc: anyio.abc.Process | None = None
        self._session: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        fmt: str,
        hash_file: Path,
        *args: str,
        potfile: Path,
        session: str,
        on_event: EventSink,
    ) -> StageResult:
        """Launch john and stream progress events until it exits."""
        argv = self._build_argv(
            fmt=fmt,
            hash_file=hash_file,
            extra_args=list(args),
            potfile=potfile,
            session=session,
        )
        log.info("john_start", session=session, fmt=fmt, argv=argv)
        self._session = session
        start = time.time()
        stats = StageStats()

        self._proc = await open_managed_process(
            argv,
            cwd=self._john_run_dir,
            stdout=__import__("subprocess").PIPE,
            stderr=__import__("subprocess").PIPE,
        )
        proc = self._proc

        try:
            async with anyio.create_task_group() as tg:
                tg.start_soon(self._stream_stderr, proc, on_event, stats, session)
                tg.start_soon(self._poll_status, session, on_event, stats, proc)
        except Exception as exc:
            log.warning("john_stream_error", error=str(exc))
        finally:
            await proc.wait()

        elapsed = time.time() - start
        password = _read_potfile_new(potfile, start)

        if password is not None:
            log.info("john_found", session=session, elapsed=elapsed)
            return StageResult(
                outcome=StageOutcome.FOUND,
                password=password,
                elapsed_seconds=elapsed,
                stats=stats,
                restore_token=session,
            )

        log.info("john_exhausted", session=session, elapsed=elapsed)
        return StageResult(
            outcome=StageOutcome.EXHAUSTED,
            password=None,
            elapsed_seconds=elapsed,
            stats=stats,
            restore_token=session,
        )

    async def pause(self) -> None:
        """Pause the running john process via CTRL_BREAK (Windows) / SIGTERM."""
        proc = self._proc
        if proc is None:
            return
        if proc.pid is not None:
            send_ctrl_break(proc.pid)
        self._proc = None

    async def resume(
        self,
        session: str,
        hash_file: Path,
        potfile: Path,
        on_event: EventSink,
    ) -> StageResult:
        """Resume a previously paused john session."""
        argv = [str(self._binary), f"--restore={session}"]
        log.info("john_resume", session=session)
        self._session = session
        start = time.time()
        stats = StageStats()

        self._proc = await open_managed_process(
            argv,
            cwd=self._john_run_dir,
            stdout=__import__("subprocess").PIPE,
            stderr=__import__("subprocess").PIPE,
        )
        proc = self._proc

        try:
            async with anyio.create_task_group() as tg:
                tg.start_soon(self._stream_stderr, proc, on_event, stats, session)
                tg.start_soon(self._poll_status, session, on_event, stats, proc)
        except Exception as exc:
            log.warning("john_resume_stream_error", error=str(exc))
        finally:
            await proc.wait()

        elapsed = time.time() - start
        password = _read_potfile_new(potfile, start)

        if password is not None:
            return StageResult(
                outcome=StageOutcome.FOUND,
                password=password,
                elapsed_seconds=elapsed,
                stats=stats,
                restore_token=session,
            )
        return StageResult(
            outcome=StageOutcome.EXHAUSTED,
            password=None,
            elapsed_seconds=elapsed,
            stats=stats,
            restore_token=session,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_argv(
        self,
        *,
        fmt: str,
        hash_file: Path,
        extra_args: list[str],
        potfile: Path,
        session: str,
    ) -> list[str]:
        return [
            str(self._binary),
            f"--session={session}",
            f"--pot={potfile}",
            f"--format={fmt}",
            *extra_args,
            str(hash_file),
        ]

    @staticmethod
    async def _stream_stderr(
        proc: anyio.abc.Process,
        on_event: EventSink,
        stats: StageStats,
        session: str,
    ) -> None:
        """Read john's stderr for progress output."""
        assert proc.stderr is not None
        buf = b""
        async for chunk in proc.stderr:
            buf += chunk
            while b"\n" in buf:
                line_bytes, buf = buf.split(b"\n", 1)
                line = line_bytes.decode(errors="replace").strip()
                if not line:
                    continue
                m = _PROGRESS_RE.search(line)
                if m:
                    cracked = int(m.group(1))
                    pct = float(m.group(2))
                    rate = int(m.group(3))
                    stats.candidates_tested = max(stats.candidates_tested, cracked)
                    if float(rate) > stats.peak_candidates_per_sec:
                        stats.peak_candidates_per_sec = float(rate)
                    evt = StageEvent(
                        ts=time.time(),
                        kind="progress",
                        payload={
                            "cracked": cracked,
                            "pct": pct,
                            "rate_ps": rate,
                            "session": session,
                        },
                    )
                    await on_event(evt)
                else:
                    log.debug("john_stderr_line", line=line)

    async def _poll_status(
        self,
        session: str,
        on_event: EventSink,
        stats: StageStats,
        proc: anyio.abc.Process,
    ) -> None:
        """Periodically run ``john --status`` and emit a progress event."""
        while True:
            await anyio.sleep(_POLL_INTERVAL_S)
            if proc.returncode is not None:
                break
            try:
                status_argv = [str(self._binary), f"--status={session}"]
                result = await anyio.run_process(
                    status_argv,
                    cwd=self._john_run_dir,
                    check=False,
                )
                output = result.stdout.decode(errors="replace")
                m = _PROGRESS_RE.search(output)
                if m:
                    cracked = int(m.group(1))
                    pct = float(m.group(2))
                    rate = int(m.group(3))
                    stats.candidates_tested = max(stats.candidates_tested, cracked)
                    if float(rate) > stats.peak_candidates_per_sec:
                        stats.peak_candidates_per_sec = float(rate)
                    evt = StageEvent(
                        ts=time.time(),
                        kind="progress",
                        payload={
                            "cracked": cracked,
                            "pct": pct,
                            "rate_ps": rate,
                            "session": session,
                            "source": "poll",
                        },
                    )
                    await on_event(evt)
            except Exception as exc:
                log.debug("john_poll_error", error=str(exc))


def _read_potfile_new(potfile: Path, since_epoch: float) -> str | None:
    """Return the password from the most recently added potfile entry, or None."""
    if not potfile.is_file():
        return None
    try:
        # potfile format: hash:password  (one per line)
        # We pick the last non-empty line as the most recent crack result.
        lines = potfile.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            if ":" in line:
                return line.split(":", 1)[1]
    except OSError:
        pass
    return None
