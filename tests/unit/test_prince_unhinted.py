from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from uzpr.core.stages.protocol import Hints, StageContext
from uzpr.core.stages.s10_prince import PrinceStage
from uzpr.engines.tool_manager import ToolNotFoundError


def _make_ctx(tmp_path: Path) -> StageContext:
    work_dir = tmp_path / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    return StageContext(
        session_id="s",
        stage_id="stage-10",
        stage_no=10,
        archive_path=tmp_path / "a.zip",
        hash_file=tmp_path / "h.txt",
        archive_format="zip-aes",
        hashcat_mode=13600,
        hints=Hints(),
        budget_seconds=1.0,
        work_dir=work_dir,
        shared_potfile=tmp_path / "pot",
        tried_candidates_db=tmp_path / "tried.db",
        gpu_devices=(),
        low_power=False,
    )


@pytest.mark.anyio
async def test_prepare_unhinted_returns_positive_prior(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    stage = PrinceStage()

    # Force pp64 to be "found" and provide a top_dict on disk so the unhinted
    # path is exercised.
    top = tmp_path / "top10k.txt"
    top.write_text("a\nb\n", encoding="utf-8")

    with (
        patch("uzpr.core.stages.s10_prince.find_tool", return_value=Path("pp64")),
        patch("uzpr.core.stages.s10_prince._find_top_dict", return_value=top),
    ):
        plan = await stage.prepare(ctx)

    assert plan.prior_probability > 0.0
    assert plan.prior_probability == pytest.approx(0.05)


@pytest.mark.anyio
async def test_prepare_hinted_uses_higher_prior(tmp_path: Path) -> None:
    ctx_base = _make_ctx(tmp_path)
    ctx = StageContext(
        session_id=ctx_base.session_id,
        stage_id=ctx_base.stage_id,
        stage_no=ctx_base.stage_no,
        archive_path=ctx_base.archive_path,
        hash_file=ctx_base.hash_file,
        archive_format=ctx_base.archive_format,
        hashcat_mode=ctx_base.hashcat_mode,
        hints=Hints(stems=("alpha", "beta")),
        budget_seconds=ctx_base.budget_seconds,
        work_dir=ctx_base.work_dir,
        shared_potfile=ctx_base.shared_potfile,
        tried_candidates_db=ctx_base.tried_candidates_db,
        gpu_devices=ctx_base.gpu_devices,
        low_power=ctx_base.low_power,
    )
    stage = PrinceStage()

    with patch("uzpr.core.stages.s10_prince.find_tool", return_value=Path("pp64")):
        plan = await stage.prepare(ctx)

    assert plan.prior_probability == pytest.approx(0.10)


@pytest.mark.anyio
async def test_prepare_skips_when_pp64_missing(tmp_path: Path) -> None:
    ctx = _make_ctx(tmp_path)
    stage = PrinceStage()

    with patch(
        "uzpr.core.stages.s10_prince.find_tool",
        side_effect=ToolNotFoundError("pp64"),
    ):
        plan = await stage.prepare(ctx)

    assert plan.prior_probability == 0.0


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
