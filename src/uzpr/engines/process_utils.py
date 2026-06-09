from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Any

import anyio
import anyio.abc

CREATE_NEW_PROCESS_GROUP: int = 0x00000200


async def open_managed_process(
    argv: list[str],
    cwd: Path,
    **kwargs: Any,
) -> anyio.abc.Process:
    """Spawn a process in a new process group.

    On Windows passes ``creationflags=CREATE_NEW_PROCESS_GROUP`` so that
    ``GenerateConsoleCtrlEvent`` can be used for graceful pause/resume.
    """
    if sys.platform == "win32":
        kwargs.setdefault("creationflags", CREATE_NEW_PROCESS_GROUP)

    return await anyio.open_process(argv, cwd=cwd, **kwargs)


def send_ctrl_break(pid: int) -> None:
    """Send CTRL_BREAK to a Windows process group for graceful stop.

    On non-Windows platforms sends SIGTERM instead.
    """
    if sys.platform == "win32":
        import ctypes

        # CTRL_BREAK_EVENT = 1
        ctypes.windll.kernel32.GenerateConsoleCtrlEvent(1, pid)  # type: ignore[attr-defined]
    else:
        import signal

        os.kill(pid, signal.SIGTERM)


async def terminate_with_grace(
    proc: anyio.abc.Process,
    sigterm_after_s: float = 7.0,
    sigkill_after_s: float = 10.0,
) -> None:
    """Escalate termination: SIGTERM → wait → SIGKILL.

    Tries a graceful terminate first; if the process is still alive after
    *sigterm_after_s* seconds it is killed unconditionally after a further
    *sigkill_after_s* seconds.
    """
    try:
        proc.terminate()
    except Exception:
        pass

    with anyio.move_on_after(sigterm_after_s):
        await proc.wait()
        return

    # Still running – escalate to kill.
    try:
        proc.kill()
    except Exception:
        pass

    with anyio.move_on_after(sigkill_after_s):
        await proc.wait()
