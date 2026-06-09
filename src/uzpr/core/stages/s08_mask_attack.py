from __future__ import annotations

import time
from pathlib import Path

import anyio

from uzpr.core.stages.protocol import (
    EventSink,
    StagePlan,
    StageContext,
    StageEvent,
    StageOutcome,
    StageResult,
    StageStats,
)
from uzpr.engines.hashcat import HashcatRunner
from uzpr.engines.tool_manager import find_tool
from uzpr.util.logging import get_logger

log = get_logger(__name__)

# 95 printable ASCII characters in the ?a charset
_CHARSET_SIZE = 95

_SKIPPED_PLAN = StagePlan(
    estimated_keyspace=0,
    estimated_candidates_per_sec=0.0,
    prior_probability=0.0,
    requires_gpu=True,
    can_resume=True,
)

# Generic masks used when no hints are available
_GENERIC_MASKS = [
    "?l?l?l?l?l?l",
    "?l?l?l?l?l?l?l?l",
    "?d?d?d?d?d?d",
    "?d?d?d?d?d?d?d?d",
    "?l?l?l?l?d?d",
    "?u?l?l?l?l?d?d",
    "?u?l?l?l?l?l?d?d",
    "?a?a?a?a?a?a?a?a",
]


def _estimate_keyspace(masks: list[str]) -> int:
    """Estimate keyspace as sum of charset_size^len for each mask pattern.

    Each ?x token counts as one character position regardless of charset.
    Non-token characters are treated as literal (size 1).
    """
    total = 0
    for mask in masks:
        # Count the number of ?x tokens in the mask
        positions = 0
        i = 0
        while i < len(mask):
            if mask[i] == "?" and i + 1 < len(mask):
                positions += 1
                i += 2
            else:
                # literal character — contributes exactly 1 candidate per position
                positions += 1
                i += 1
        total += _CHARSET_SIZE ** positions
    return total


def _write_hcmask(masks: list[str], path: Path) -> None:
    """Write a list of mask strings to an .hcmask file."""
    path.write_text("\n".join(masks) + "\n", encoding="utf-8")


class MaskAttackStage:
    stage_no: int = 8
    name: str = "Mask attack (derived)"
    engine: str = "hashcat"

    def __init__(self) -> None:
        self._stats = StageStats()
        self._active_runner: HashcatRunner | None = None

    async def prepare(self, ctx: StageContext) -> StagePlan:
        hints = ctx.hints

        # Try to derive masks from hints; fall back to generic masks
        hints_empty = (
            not hints.stems
            and not hints.first_names
            and not hints.nicknames
            and not hints.pet_names
            and not hints.places
            and not hints.prefixes
            and not hints.suffixes
            and hints.partial_mask is None
            and not hints.dates
        )

        if hints_empty:
            masks = _GENERIC_MASKS
        else:
            try:
                from uzpr.wordlist.masks import derive_masks  # type: ignore[import-untyped]

                hcmask_path = derive_masks(hints)
                masks = [
                    line
                    for line in hcmask_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                ]
            except Exception:
                masks = _GENERIC_MASKS

        keyspace = _estimate_keyspace(masks)
        return StagePlan(
            estimated_keyspace=keyspace,
            estimated_candidates_per_sec=5_000_000.0,
            prior_probability=0.10,
            requires_gpu=True,
            can_resume=True,
        )

    async def run(self, ctx: StageContext, on_event: EventSink) -> StageResult:
        self._stats = StageStats()
        start = time.monotonic()

        if ctx.hashcat_mode is None:
            return StageResult(
                outcome=StageOutcome.SKIPPED,
                password=None,
                elapsed_seconds=0.0,
                stats=self._stats,
                restore_token=None,
            )

        hints = ctx.hints
        hints_empty = (
            not hints.stems
            and not hints.first_names
            and not hints.nicknames
            and not hints.pet_names
            and not hints.places
            and not hints.prefixes
            and not hints.suffixes
            and hints.partial_mask is None
            and not hints.dates
        )

        masks_hcmask_path = ctx.work_dir / "masks.hcmask"

        if hints_empty:
            _write_hcmask(_GENERIC_MASKS, masks_hcmask_path)
        else:
            try:
                from uzpr.wordlist.masks import derive_masks  # type: ignore[import-untyped]

                derived_path = derive_masks(hints)
                masks_hcmask_path = derived_path
            except Exception as exc:
                log.warning("mask_derive_failed", error=str(exc))
                _write_hcmask(_GENERIC_MASKS, masks_hcmask_path)

        binary = find_tool("hashcat")
        runner = HashcatRunner(binary, ctx.work_dir)
        self._active_runner = runner

        result: StageResult | None = None

        async def _body() -> None:
            nonlocal result
            result = await runner.run(
                ctx.hashcat_mode,  # type: ignore[arg-type]
                3,
                ctx.hash_file,
                str(masks_hcmask_path),
                potfile=ctx.shared_potfile,
                session=ctx.stage_id,
                on_event=on_event,
                low_power=ctx.low_power,
                gpu_devices=ctx.gpu_devices,
            )

        with anyio.move_on_after(ctx.budget_seconds):
            await _body()

        self._active_runner = None
        elapsed = time.monotonic() - start

        if result is None:
            await on_event(
                StageEvent(
                    ts=time.time(),
                    kind="log",
                    payload={"msg": "mask_attack budget exhausted, stage aborted"},
                )
            )
            return StageResult(
                outcome=StageOutcome.ABORTED,
                password=None,
                elapsed_seconds=elapsed,
                stats=self._stats,
                restore_token=ctx.stage_id,
            )

        # Carry stats from the runner result back
        self._stats = result.stats
        return StageResult(
            outcome=result.outcome,
            password=result.password,
            elapsed_seconds=elapsed,
            stats=self._stats,
            restore_token=result.restore_token,
            error=result.error,
        )

    async def cancel(self) -> None:
        runner = self._active_runner
        if runner is not None:
            await runner.pause()
