from __future__ import annotations

import sys
import zipfile
from pathlib import Path
from typing import Literal

import platformdirs

from uzpr.util.logging import get_logger
from uzpr.util.paths import install_dir

log = get_logger(__name__)

ToolName = Literal["hashcat", "john", "zip2john", "rar2john", "bkcrack", "pp64"]

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_APP_NAME = "UltimateZipPasswordRecover"

# Mapping: tool name → (subdir_parts, exe_win, exe_posix)
# subdir_parts are joined under tools/<subdir>/
_TOOL_MAP: dict[str, tuple[tuple[str, ...], str, str]] = {
    "hashcat":  (("hashcat",),              "hashcat.exe",  "hashcat"),
    "john":     (("john", "run"),           "john.exe",     "john"),
    "zip2john": (("john", "run"),           "zip2john.exe", "zip2john"),
    "rar2john": (("john", "run"),           "rar2john.exe", "rar2john"),
    "bkcrack":  (("bkcrack",),              "bkcrack.exe",  "bkcrack"),
    "pp64":     (("john", "run"),           "pp64.exe",     "pp64"),
}

# Download URLs for each tool *package* (one URL may satisfy multiple tools)
_DOWNLOAD_URLS: dict[str, str] = {
    "hashcat":  "https://hashcat.net/files/hashcat-6.2.6.7z",
    "john":     "https://www.openwall.com/john/k/john-1.9.0-jumbo-1-win64.7z",
    "bkcrack":  "https://github.com/kimci86/bkcrack/releases/download/v1.7.0/bkcrack-1.7.0-win64.zip",
}

# Which "package" does each tool belong to?
_TOOL_PACKAGE: dict[str, str] = {
    "hashcat":  "hashcat",
    "john":     "john",
    "zip2john": "john",
    "rar2john": "john",
    "pp64":     "john",
    "bkcrack":  "bkcrack",
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ToolNotFoundError(FileNotFoundError):
    """Raised when a required external tool binary is not found."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_tools_dir() -> Path:
    return Path(platformdirs.user_data_dir(_APP_NAME, False)) / "tools"


def _candidate_dirs() -> list[Path]:
    """Ordered list of base *tools* directories to search."""
    candidates: list[Path] = []

    # 1. PyInstaller bundle
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "tools")

    # 2. install_dir()
    candidates.append(install_dir() / "tools")

    # 3. platformdirs user data
    candidates.append(_user_tools_dir())

    return candidates


def _exe_name(name: str) -> str:
    subdir_parts, exe_win, exe_posix = _TOOL_MAP[name]
    return exe_win if sys.platform == "win32" else exe_posix


def _rel_path(name: str) -> Path:
    """Relative path from a tools/ root to the binary."""
    subdir_parts, exe_win, exe_posix = _TOOL_MAP[name]
    exe = exe_win if sys.platform == "win32" else exe_posix
    p = Path()
    for part in subdir_parts:
        p = p / part
    return p / exe


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_tool(name: ToolName) -> Path:
    """Locate a bundled tool binary.

    Searches (in order): PyInstaller bundle, install_dir, platformdirs user
    data.  Raises :class:`ToolNotFoundError` if not found.
    """
    rel = _rel_path(name)
    for base in _candidate_dirs():
        candidate = base / rel
        if candidate.is_file():
            log.debug("tool_found", tool=name, path=str(candidate))
            return candidate

    raise ToolNotFoundError(
        f"Tool '{name}' not found. Searched: "
        + ", ".join(str(b / rel) for b in _candidate_dirs())
    )


async def ensure_tool(name: ToolName) -> Path:
    """Locate tool, downloading its package if absent.

    Returns the path to the binary after locating or downloading it.
    """
    try:
        return find_tool(name)
    except ToolNotFoundError:
        pass

    package = _TOOL_PACKAGE[name]
    url = _DOWNLOAD_URLS[package]
    dest_dir = _user_tools_dir() / package
    dest_dir.mkdir(parents=True, exist_ok=True)

    log.info("downloading_tool_package", package=package, url=url)
    archive_path = _user_tools_dir() / Path(url).name
    await _download(url, archive_path)

    log.info("extracting_tool_package", package=package, dest=str(dest_dir))
    await _extract(archive_path, dest_dir)

    try:
        archive_path.unlink()
    except OSError:
        pass

    return find_tool(name)


def list_status() -> dict[str, dict[str, object]]:
    """Return install status for all known tools."""
    result: dict[str, dict[str, object]] = {}
    for name in _TOOL_MAP:
        try:
            path = find_tool(name)  # type: ignore[arg-type]
            result[name] = {"found": True, "path": str(path)}
        except ToolNotFoundError:
            result[name] = {"found": False, "path": None}
    return result


# ---------------------------------------------------------------------------
# Download + extract helpers
# ---------------------------------------------------------------------------

async def _download(url: str, dest: Path) -> None:
    """Stream-download *url* to *dest*."""
    import httpx

    async with httpx.AsyncClient(follow_redirects=True, timeout=300) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0)) or None
            received = 0
            with dest.open("wb") as fh:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    fh.write(chunk)
                    received += len(chunk)
                    if total:
                        pct = received / total * 100
                        log.debug("download_progress", url=url, pct=f"{pct:.1f}")
    log.info("download_complete", dest=str(dest))


async def _extract(archive: Path, dest: Path) -> None:
    """Extract a .7z or .zip archive into *dest*."""
    suffix = archive.suffix.lower()
    if suffix == ".7z":
        import py7zr  # type: ignore[import-untyped]
        import anyio

        def _do_extract() -> None:
            with py7zr.SevenZipFile(archive, mode="r") as sz:
                sz.extractall(path=dest)

        await anyio.to_thread.run_sync(_do_extract)
    elif suffix == ".zip":
        import anyio

        def _do_unzip() -> None:
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(dest)

        await anyio.to_thread.run_sync(_do_unzip)
    else:
        raise ValueError(f"Unsupported archive format: {archive}")

    log.info("extract_complete", archive=str(archive), dest=str(dest))
