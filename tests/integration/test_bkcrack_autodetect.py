from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

# Allow importing the test-only ZipCrypto builder from scripts/
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

pytestmark = pytest.mark.external  # needs the bkcrack binary


@pytest.mark.asyncio
async def test_autodetect_defeats_random_zipcrypto_password(tmp_path: Path) -> None:
    """Stage 13 cracks a 12-char RANDOM ZipCrypto password with zero user input.

    The archive holds a STORED (uncompressed) PNG. bkcrack's known-plaintext
    attack recovers the internal keys from the deterministic 16-byte PNG header
    alone — password length/complexity is irrelevant — then decrypts the archive.
    """
    from make_zipcrypto import build_zipcrypto, make_png  # type: ignore[import-not-found]

    from uzpr.archive.detect import detect_archive
    from uzpr.core.stages.protocol import Hints, StageContext, StageEvent, StageOutcome
    from uzpr.core.stages.s13_bkcrack import BkcrackStage
    from uzpr.engines.tool_manager import ToolNotFoundError, find_tool

    try:
        find_tool("bkcrack")
    except ToolNotFoundError:
        pytest.skip("bkcrack binary not installed")

    archive = tmp_path / "secret.zip"
    password = "rT5#uY8@vW1$"  # 12 random chars — uncrackable by brute force
    build_zipcrypto(archive, "image.png", make_png(120), password.encode())

    info = detect_archive(archive)
    assert info.format == "zip-classic"

    ctx = StageContext(
        session_id="t",
        stage_id="s13",
        stage_no=13,
        archive_path=archive,
        hash_file=tmp_path / "h.hash",
        archive_format=info.format,
        hashcat_mode=None,
        hints=Hints(),  # empty — no plaintext_sample, no hints
        budget_seconds=120.0,
        work_dir=tmp_path,
        shared_potfile=tmp_path / "p.pot",
        tried_candidates_db=tmp_path / "t.db",
        gpu_devices=(),
        low_power=False,
    )

    async def on_event(_e: StageEvent) -> None:
        return None

    result = await BkcrackStage().run(ctx, on_event)

    assert result.outcome == StageOutcome.FOUND
    decrypted = tmp_path / "decrypted.zip"
    assert decrypted.exists(), "archive should be decrypted from recovered keys"
    with zipfile.ZipFile(decrypted) as zf:
        recovered = zf.read("image.png")
    assert recovered[:16].hex() == "89504e470d0a1a0a0000000d49484452"
