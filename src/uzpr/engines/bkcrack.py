from __future__ import annotations

import re
import time
from pathlib import Path

import anyio
import anyio.abc

from uzpr.core.stages.protocol import EventSink, StageEvent
from uzpr.engines.process_utils import open_managed_process
from uzpr.util.logging import get_logger

log = get_logger(__name__)

# Magic bytes for ZIP local file header
_ZIP_MAGIC = b"PK\x03\x04"

# Regex patterns for bkcrack output
_PROGRESS_RE = re.compile(r"(\d+\.\d+)%")
_KEYS_RE = re.compile(r"Keys:\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+([0-9a-fA-F]+)")
_PASSWORD_RE = re.compile(r"Password:\s+(.+)")


class BkcrackRunner:
    """Wraps the bkcrack binary for ZipCrypto known-plaintext attacks."""

    def __init__(self, binary: Path, work_dir: Path) -> None:
        self._binary = binary
        self._work_dir = work_dir

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def recover_keys(
        self,
        archive: Path,
        entry: str,
        plain: Path,
        on_event: EventSink,
    ) -> tuple[int, int, int] | None:
        """Attempt to recover the three internal ZipCrypto keys.

        Returns a tuple of three ints (k0, k1, k2) on success, or None if
        bkcrack exits with a non-zero code (keys not found).
        """
        plain_args = _build_plain_args(plain, entry)
        argv = [
            str(self._binary),
            "-C",
            str(archive),
            "-c",
            entry,
            *plain_args,
        ]
        log.info(
            "bkcrack_recover_keys_start",
            archive=str(archive),
            entry=entry,
            argv=argv,
        )

        proc = await open_managed_process(
            argv,
            cwd=self._work_dir,
            stdout=__import__("subprocess").PIPE,
            stderr=__import__("subprocess").PIPE,
        )

        keys: tuple[int, int, int] | None = None
        buf = b""

        async def _read_output(stream: anyio.abc.ByteReceiveStream) -> None:
            nonlocal keys
            nonlocal buf
            async for chunk in stream:
                buf += chunk
                while b"\n" in buf:
                    line_bytes, buf = buf.split(b"\n", 1)
                    line = line_bytes.decode(errors="replace").strip()
                    if not line:
                        continue
                    log.debug("bkcrack_output", line=line)

                    m_pct = _PROGRESS_RE.search(line)
                    if m_pct:
                        evt = StageEvent(
                            ts=time.time(),
                            kind="progress",
                            payload={"pct": float(m_pct.group(1))},
                        )
                        await on_event(evt)

                    m_keys = _KEYS_RE.search(line)
                    if m_keys:
                        keys = (
                            int(m_keys.group(1), 16),
                            int(m_keys.group(2), 16),
                            int(m_keys.group(3), 16),
                        )
                        log.info("bkcrack_keys_found", keys=keys)

        # bkcrack may write to stdout or stderr depending on version; read both
        try:
            async with anyio.create_task_group() as tg:
                if proc.stdout is not None:
                    tg.start_soon(_read_output, proc.stdout)
                if proc.stderr is not None:
                    tg.start_soon(_read_output, proc.stderr)
        except Exception as exc:
            log.warning("bkcrack_read_error", error=str(exc))
        finally:
            await proc.wait()

        rc = proc.returncode
        if rc != 0:
            log.info("bkcrack_keys_not_found", rc=rc)
            return None

        return keys

    async def decrypt(
        self,
        archive: Path,
        keys: tuple[int, int, int],
        out: Path,
    ) -> None:
        """Decrypt the entire archive using the known keys."""
        k0, k1, k2 = keys
        # bkcrack expects 8-char hex WITHOUT the 0x prefix (e.g. "5b0d2400").
        argv = [
            str(self._binary),
            "-C",
            str(archive),
            "-k",
            f"{k0:08x}",
            f"{k1:08x}",
            f"{k2:08x}",
            "-D",
            str(out),
        ]
        log.info("bkcrack_decrypt", archive=str(archive), out=str(out))
        result = await anyio.run_process(argv, cwd=self._work_dir, check=False)
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").strip()
            raise RuntimeError(f"bkcrack decrypt failed (rc={result.returncode}): {stderr}")

    async def recover_password(
        self,
        keys: tuple[int, int, int],
        length_range: tuple[int, int],
        on_event: EventSink,
    ) -> str | None:
        """Attempt to recover the original password from keys via brute-force.

        Returns the password string if found, or None.
        """
        k0, k1, k2 = keys
        lo, hi = length_range
        # bkcrack expects 8-char hex WITHOUT the 0x prefix (e.g. "5b0d2400").
        argv = [
            str(self._binary),
            "-k",
            f"{k0:08x}",
            f"{k1:08x}",
            f"{k2:08x}",
            "-r",
            f"{lo}..{hi}",
            "?p",
        ]
        log.info(
            "bkcrack_recover_password",
            keys=keys,
            length_range=length_range,
        )

        proc = await open_managed_process(
            argv,
            cwd=self._work_dir,
            stdout=__import__("subprocess").PIPE,
            stderr=__import__("subprocess").PIPE,
        )

        found_password: str | None = None
        buf = b""

        async def _read_pw_output(stream: anyio.abc.ByteReceiveStream) -> None:
            nonlocal found_password
            nonlocal buf
            async for chunk in stream:
                buf += chunk
                while b"\n" in buf:
                    line_bytes, buf = buf.split(b"\n", 1)
                    line = line_bytes.decode(errors="replace").strip()
                    if not line:
                        continue
                    log.debug("bkcrack_pw_output", line=line)

                    m_pct = _PROGRESS_RE.search(line)
                    if m_pct:
                        evt = StageEvent(
                            ts=time.time(),
                            kind="progress",
                            payload={"pct": float(m_pct.group(1))},
                        )
                        await on_event(evt)

                    m_pw = _PASSWORD_RE.search(line)
                    if m_pw:
                        found_password = m_pw.group(1).strip()
                        log.info("bkcrack_password_recovered", password=found_password)

        try:
            async with anyio.create_task_group() as tg:
                if proc.stdout is not None:
                    tg.start_soon(_read_pw_output, proc.stdout)
                if proc.stderr is not None:
                    tg.start_soon(_read_pw_output, proc.stderr)
        except Exception as exc:
            log.warning("bkcrack_pw_read_error", error=str(exc))
        finally:
            await proc.wait()

        return found_password


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_zip(path: Path) -> bool:
    """Return True if the file starts with the ZIP local file magic bytes."""
    try:
        with path.open("rb") as fh:
            return fh.read(4) == _ZIP_MAGIC
    except OSError:
        return False


def _build_plain_args(plain: Path, entry: str) -> list[str]:
    """Build the bkcrack plaintext arguments.

    If *plain* is a ZIP file use ``-P plain -p entry``; otherwise use
    ``-p plain`` (raw file, assuming stored entry).
    """
    if _is_zip(plain):
        return ["-P", str(plain), "-p", entry]
    return ["-p", str(plain)]
