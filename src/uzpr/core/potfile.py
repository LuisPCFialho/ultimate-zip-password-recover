from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl


class SharedPotfile:
    """Advisory-locked shared potfile for cross-stage deduplication.

    Each entry is a single UTF-8 line in the format ``hash:password\\n``.
    Locking is advisory: exclusive on write, shared on read (POSIX); on
    Windows msvcrt.locking is used as a best-effort byte-range lock.
    """

    def __init__(self, path: Path) -> None:
        """Prepare the potfile at *path*, creating it if absent.

        Args:
            path: File system path for the potfile.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch()
        self._path = path

    # ------------------------------------------------------------------
    # Platform lock helpers
    # ------------------------------------------------------------------

    @contextmanager
    def _locked_append(self) -> Generator[object, None, None]:
        """Context manager: open for append with an exclusive advisory lock.

        Yields the open text file handle so callers write through the locked fd.
        """
        with self._path.open("a", encoding="utf-8") as fh:
            if sys.platform == "win32":
                fd = fh.fileno()
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
                except OSError:
                    msvcrt.locking(fd, msvcrt.LK_LOCK, 1)  # type: ignore[attr-defined]
                try:
                    yield fh
                    fh.flush()
                finally:
                    try:
                        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
                    except OSError:
                        pass
            else:
                fcntl.flock(fh, fcntl.LOCK_EX)  # type: ignore[attr-defined]
                try:
                    yield fh
                    fh.flush()
                finally:
                    fcntl.flock(fh, fcntl.LOCK_UN)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_entry(self, hash_str: str, password: str) -> None:
        """Append a ``hash:password`` line to the potfile under an exclusive lock.

        Args:
            hash_str: Hash identifier string (no colons expected as first field).
            password: Recovered plain-text password.
        """
        with self._locked_append() as fh:
            fh.write(f"{hash_str}:{password}\n")  # type: ignore[union-attr]

    def iter_entries(self) -> Generator[tuple[str, str], None, None]:
        """Yield ``(hash_str, password)`` pairs from the potfile under a shared lock.

        Blank lines and lines without a colon separator are silently skipped.
        """
        with self._path.open("r", encoding="utf-8") as fh:
            if sys.platform != "win32":
                fcntl.flock(fh, fcntl.LOCK_SH)  # type: ignore[attr-defined]
            try:
                for raw_line in fh:
                    line = raw_line.rstrip("\n")
                    if not line:
                        continue
                    sep = line.find(":")
                    if sep < 0:
                        continue
                    yield line[:sep], line[sep + 1:]
            finally:
                if sys.platform != "win32":
                    fcntl.flock(fh, fcntl.LOCK_UN)  # type: ignore[attr-defined]
