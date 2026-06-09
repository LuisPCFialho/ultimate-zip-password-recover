from __future__ import annotations

import json
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
    terminate_with_grace,
)
from uzpr.util.logging import get_logger

log = get_logger(__name__)

# hashcat exit codes
_EC_EXHAUSTED = 1


class HashcatRunner:
    """Wraps the hashcat binary for cracking and benchmarking."""

    def __init__(self, binary: Path, work_dir: Path) -> None:
        self._binary = binary
        self._work_dir = work_dir
        self._proc: anyio.abc.Process | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        mode: int,
        attack: int,
        hash_file: Path,
        *args: str,
        potfile: Path,
        session: str,
        on_event: EventSink,
        low_power: bool = False,
        gpu_devices: tuple[int, ...] = (),
    ) -> StageResult:
        """Launch hashcat and stream progress events until it exits."""
        argv = self._build_argv(
            mode=mode,
            attack=attack,
            hash_file=hash_file,
            extra_args=list(args),
            potfile=potfile,
            session=session,
            low_power=low_power,
            gpu_devices=gpu_devices,
        )
        log.info("hashcat_start", session=session, mode=mode, attack=attack, argv=argv)
        start = time.time()
        stats = StageStats()

        import subprocess as _sp

        # hashcat must run from its own directory so it can find OpenCL/ kernels
        hashcat_dir = self._binary.parent

        self._proc = await open_managed_process(
            argv,
            cwd=hashcat_dir,
            stdout=_sp.PIPE,
            stderr=_sp.DEVNULL,
            stdin=_sp.PIPE,
        )
        proc = self._proc

        try:
            async with anyio.create_task_group() as tg:
                tg.start_soon(self._stream_stdout, proc, on_event, stats)
        except Exception as exc:
            log.warning("hashcat_stream_error", error=str(exc))
        finally:
            await proc.wait()

        elapsed = time.time() - start
        rc = proc.returncode

        if rc == 0 or rc == _EC_EXHAUSTED:
            out_file = self._work_dir / f"{session}.out"
            password = _read_outfile(out_file)
            if password is not None:
                log.info("hashcat_found", session=session, elapsed=elapsed)
                return StageResult(
                    outcome=StageOutcome.FOUND,
                    password=password,
                    elapsed_seconds=elapsed,
                    stats=stats,
                    restore_token=session,
                )
            log.info("hashcat_exhausted", session=session, elapsed=elapsed)
            return StageResult(
                outcome=StageOutcome.EXHAUSTED,
                password=None,
                elapsed_seconds=elapsed,
                stats=stats,
                restore_token=session,
            )

        log.error("hashcat_failed", session=session, rc=rc, elapsed=elapsed)
        return StageResult(
            outcome=StageOutcome.FAILED,
            password=None,
            elapsed_seconds=elapsed,
            stats=stats,
            restore_token=session,
            error=f"hashcat exited with code {rc}",
        )

    async def pause(self) -> None:
        """Pause the running hashcat process gracefully."""
        proc = self._proc
        if proc is None:
            return
        try:
            if proc.stdin is not None:
                await proc.stdin.send(b"q\n")
        except Exception:
            pass
        await terminate_with_grace(proc, sigterm_after_s=7.0, sigkill_after_s=10.0)
        self._proc = None

    async def resume(
        self,
        session: str,
        hash_file: Path,
        potfile: Path,
        on_event: EventSink,
    ) -> StageResult:
        """Resume a previously paused hashcat session."""
        argv = [
            str(self._binary),
            f"--session={session}",
            "--restore",
            f"--restore-file-path={self._work_dir}",
        ]
        log.info("hashcat_resume", session=session)
        start = time.time()
        stats = StageStats()

        import subprocess as _sp

        self._proc = await open_managed_process(
            argv,
            cwd=self._work_dir,
            stdout=_sp.PIPE,
            stderr=_sp.DEVNULL,
            stdin=_sp.PIPE,
        )
        proc = self._proc

        try:
            async with anyio.create_task_group() as tg:
                tg.start_soon(self._stream_stdout, proc, on_event, stats)
        except Exception as exc:
            log.warning("hashcat_resume_stream_error", error=str(exc))
        finally:
            await proc.wait()

        elapsed = time.time() - start
        rc = proc.returncode

        out_file = self._work_dir / f"{session}.out"
        password = _read_outfile(out_file)

        if rc == 0 or rc == _EC_EXHAUSTED:
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

        return StageResult(
            outcome=StageOutcome.FAILED,
            password=None,
            elapsed_seconds=elapsed,
            stats=stats,
            restore_token=session,
            error=f"hashcat exited with code {rc}",
        )

    async def benchmark(self, mode: int, device_id: int) -> float:
        """Run a short benchmark and return throughput in H/s."""
        argv = [
            str(self._binary),
            "-b",
            "-m",
            str(mode),
            "-d",
            str(device_id),
            "--runtime=10",
            "-O",
            "-w",
            "2",
            "--machine-readable",
        ]
        log.info("hashcat_benchmark", mode=mode, device_id=device_id)
        proc = await open_managed_process(argv, cwd=self._work_dir, stdout=anyio.abc.ByteStream)  # type: ignore[arg-type]
        lines: list[str] = []
        assert proc.stdout is not None
        async for raw in proc.stdout:
            lines.append(raw.decode(errors="replace").strip())
        await proc.wait()

        # Machine-readable line format: <mode>|<device>|<name>|<unit>|<speed>
        prefix = f"{mode}|"
        for line in lines:
            if line.startswith(prefix) and "|H/s|" in line:
                parts = line.split("|")
                # last part is the speed value
                try:
                    return float(parts[-1])
                except (ValueError, IndexError):
                    pass
        log.warning("hashcat_benchmark_no_result", mode=mode, device_id=device_id)
        return 0.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_argv(
        self,
        *,
        mode: int,
        attack: int,
        hash_file: Path,
        extra_args: list[str],
        potfile: Path,
        session: str,
        low_power: bool,
        gpu_devices: tuple[int, ...],
    ) -> list[str]:
        argv = [
            str(self._binary),
            "-m",
            str(mode),
            "-a",
            str(attack),
            str(hash_file),
            *extra_args,
            "--quiet",
            "--status",
            "--status-json",
            "--status-timer=2",
            f"--session={session}",
            f"--restore-file-path={self._work_dir / (session + '.restore')}",
            f"--potfile-path={potfile}",
            f"--outfile={self._work_dir / (session + '.out')}",
            "--outfile-format=2",
            "-O",
        ]

        if low_power:
            argv += ["-w", "1", "--hwmon-temp-abort=75"]
        else:
            argv += ["-w", "2"]

        if gpu_devices:
            argv += ["-d", ",".join(str(d) for d in gpu_devices)]

        return argv

    @staticmethod
    async def _stream_stdout(
        proc: anyio.abc.Process,
        on_event: EventSink,
        stats: StageStats,
    ) -> None:
        """Read stdout line-by-line, parse JSON status objects."""
        assert proc.stdout is not None
        buf = b""
        async for chunk in proc.stdout:
            buf += chunk
            while b"\n" in buf:
                line_bytes, buf = buf.split(b"\n", 1)
                line = line_bytes.decode(errors="replace").strip()
                if not line:
                    continue
                try:
                    data: dict[str, object] = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    log.debug("hashcat_non_json_line", line=line)
                    continue

                _update_stats(stats, data)
                evt = StageEvent(
                    ts=time.time(),
                    kind="progress",
                    payload={
                        "progress": data.get("progress"),
                        "speed": data.get("speed"),
                        "eta": data.get("eta"),
                        "recovered": data.get("recovered"),
                        "raw": data,
                    },
                )
                await on_event(evt)


def _update_stats(stats: StageStats, data: dict[str, object]) -> None:
    """Mutate *stats* in-place from a hashcat JSON status dict."""
    progress = data.get("progress")
    if isinstance(progress, list) and len(progress) >= 2:
        tested = progress[0]
        if isinstance(tested, int):
            stats.candidates_tested = tested

    speed = data.get("speed")
    if isinstance(speed, list):
        total_speed: float = sum(float(s) for s in speed if isinstance(s, (int, float)))
        if total_speed > stats.peak_candidates_per_sec:
            stats.peak_candidates_per_sec = total_speed


def _read_outfile(out_file: Path) -> str | None:
    """Read the first non-empty line of hashcat's outfile, return the password."""
    if not out_file.is_file():
        return None
    try:
        for raw_line in out_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            # outfile-format=2 writes only the plain password per line
            return line
    except OSError:
        pass
    return None
