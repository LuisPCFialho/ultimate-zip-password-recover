from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.asyncio
async def test_stage1_finds_correct_password(tmp_path: Path) -> None:
    """Stage 1 should find password 'test123' when it is supplied as a hint."""
    archive = FIXTURES / "test_zipcrypto.zip"
    if not archive.exists():
        pytest.skip("Run tests/fixtures/create_test_archives.py first")

    from uzpr.archive.detect import detect_archive
    from uzpr.core.stages.protocol import (
        Hints,
        StageContext,
        StageEvent,
        StageOutcome,
    )
    from uzpr.core.stages.s01_known_password import KnownPasswordStage

    info = detect_archive(archive)

    ctx = StageContext(
        session_id="test-session",
        stage_id="test-stage-1",
        stage_no=1,
        archive_path=archive,
        hash_file=tmp_path / "test.hash",
        archive_format=info.format,
        hashcat_mode=None,
        hints=Hints(full_password="test123"),
        budget_seconds=10.0,
        work_dir=tmp_path,
        shared_potfile=tmp_path / "uzpr.pot",
        tried_candidates_db=tmp_path / "tried.db",
        gpu_devices=(),
        low_power=False,
    )

    events: list[StageEvent] = []

    async def on_event(e: StageEvent) -> None:
        events.append(e)

    stage = KnownPasswordStage()
    result = await stage.run(ctx, on_event)

    assert result.outcome == StageOutcome.FOUND
    assert result.password == "test123"


@pytest.mark.asyncio
async def test_stage1_exhausted_wrong_password(tmp_path: Path) -> None:
    """Stage 1 returns EXHAUSTED when the supplied hint password is wrong."""
    archive = FIXTURES / "test_zipcrypto.zip"
    if not archive.exists():
        pytest.skip("Run tests/fixtures/create_test_archives.py first")

    from uzpr.archive.detect import detect_archive
    from uzpr.core.stages.protocol import Hints, StageContext, StageOutcome
    from uzpr.core.stages.s01_known_password import KnownPasswordStage

    info = detect_archive(archive)

    ctx = StageContext(
        session_id="test-s2",
        stage_id="test-stage-1b",
        stage_no=1,
        archive_path=archive,
        hash_file=tmp_path / "t.hash",
        archive_format=info.format,
        hashcat_mode=None,
        hints=Hints(full_password="wrongpassword"),
        budget_seconds=10.0,
        work_dir=tmp_path,
        shared_potfile=tmp_path / "uzpr.pot",
        tried_candidates_db=tmp_path / "tried.db",
        gpu_devices=(),
        low_power=False,
    )

    stage = KnownPasswordStage()
    result = await stage.run(ctx, lambda e: asyncio.sleep(0))

    assert result.outcome == StageOutcome.EXHAUSTED
