from __future__ import annotations

#!/usr/bin/env python3
"""Smoke test for the UZPR download + cracking pipeline.

Creates a temporary AES-encrypted ZIP, then exercises Stage 1 (known-password
verify) with both the correct and a wrong password.  Exits 0 on success,
1 on any failure.

Usage:
    python scripts/smoke_test.py
"""
import asyncio
import sys
import tempfile
import zipfile
from pathlib import Path

# Ensure src/ is on the path when run directly from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pyzipper  # type: ignore[import-untyped]

from uzpr.archive.detect import detect_archive
from uzpr.core.stages.protocol import (
    Hints,
    StageContext,
    StageEvent,
    StageOutcome,
)
from uzpr.core.stages.s01_known_password import KnownPasswordStage
from uzpr.util.logging import configure
from uzpr.util.paths import logs_dir

_PASSWORD = "hello123"
_WRONG_PASSWORD = "notthepassword"


def _create_test_zip(path: Path) -> None:
    """Write a small AES-256 encrypted ZIP to *path*."""
    with pyzipper.AESZipFile(
        path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        encryption=pyzipper.WZ_AES,
    ) as zf:
        zf.setpassword(_PASSWORD.encode())
        zf.writestr("smoke.txt", "UZPR smoke test payload.")


async def _run_stage1(
    archive: Path,
    work_dir: Path,
    password: str,
) -> StageOutcome:
    info = detect_archive(archive)
    ctx = StageContext(
        session_id="smoke-test",
        stage_id="smoke-stage-1",
        stage_no=1,
        archive_path=archive,
        hash_file=work_dir / "smoke.hash",
        archive_format=info.format,
        hashcat_mode=None,
        hints=Hints(full_password=password),
        budget_seconds=10.0,
        work_dir=work_dir,
        shared_potfile=work_dir / "uzpr.pot",
        tried_candidates_db=work_dir / "tried.db",
        gpu_devices=(),
        low_power=False,
    )

    async def _sink(_e: StageEvent) -> None:
        pass

    stage = KnownPasswordStage()
    result = await stage.run(ctx, _sink)
    return result.outcome


async def main() -> int:
    configure(logs_dir())

    with tempfile.TemporaryDirectory() as tmp_str:
        work = Path(tmp_str)
        archive = work / "smoke_test.zip"
        _create_test_zip(archive)

        # --- Test 1: correct password should be FOUND ---
        outcome = await _run_stage1(archive, work, _PASSWORD)
        if outcome != StageOutcome.FOUND:
            print(f"SMOKE TEST FAILED: expected FOUND, got {outcome}")
            return 1

        # --- Test 2: wrong password should be EXHAUSTED ---
        outcome = await _run_stage1(archive, work, _WRONG_PASSWORD)
        if outcome != StageOutcome.EXHAUSTED:
            print(f"SMOKE TEST FAILED: expected EXHAUSTED, got {outcome}")
            return 1

    print("SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
