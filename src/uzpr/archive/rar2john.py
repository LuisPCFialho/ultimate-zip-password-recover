from __future__ import annotations

from pathlib import Path

import anyio


async def extract_rar_hash(archive_path: Path, work_dir: Path) -> Path:
    """
    Run rar2john on a RAR archive and return the path to the hash file.

    Raises RuntimeError if the process exits with a non-zero code or produces
    no output.
    """
    from uzpr.engines.tool_manager import find_tool

    binary = find_tool("rar2john")

    result = await anyio.run_process(
        [str(binary), str(archive_path)],
        cwd=str(work_dir),
    )

    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(
            f"rar2john exited with code {result.returncode}: {stderr}"
        )

    stdout = result.stdout
    if not stdout.strip():
        raise RuntimeError("rar2john produced no output")

    hash_file = work_dir / (archive_path.stem + ".hash")
    hash_file.write_bytes(stdout)
    return hash_file
