from __future__ import annotations

import time
from pathlib import Path

import anyio

from uzpr.archive.signatures import signature_for
from uzpr.core.stages.protocol import (
    EventSink,
    StageContext,
    StageEvent,
    StageOutcome,
    StagePlan,
    StageResult,
    StageStats,
)
from uzpr.engines.bkcrack import BkcrackRunner
from uzpr.engines.tool_manager import find_tool
from uzpr.util.logging import get_logger

log = get_logger(__name__)

_SKIPPED_PLAN = StagePlan(
    estimated_keyspace=0,
    estimated_candidates_per_sec=0.0,
    prior_probability=0.0,
    requires_gpu=False,
    can_resume=False,
)


class BkcrackStage:
    stage_no: int = 13
    name: str = "Known-plaintext attack (bkcrack)"
    engine: str = "bkcrack"

    def __init__(self) -> None:
        self._stats = StageStats()
        self._active_runner: BkcrackRunner | None = None

    async def prepare(self, ctx: StageContext) -> StagePlan:
        if ctx.archive_format != "zip-classic":
            log.debug("bkcrack_skip_not_zipcrypto", format=ctx.archive_format)
            return _SKIPPED_PLAN

        # Do NOT skip when plaintext_sample is None: run() can auto-detect a
        # known-plaintext target from a STORED entry's magic header.
        return StagePlan(
            estimated_keyspace=1,
            estimated_candidates_per_sec=0.1,
            prior_probability=1.0,
            requires_gpu=False,
            can_resume=False,
        )

    async def run(self, ctx: StageContext, on_event: EventSink) -> StageResult:
        self._stats = StageStats()
        start = time.monotonic()

        if ctx.archive_format != "zip-classic":
            return StageResult(
                outcome=StageOutcome.SKIPPED,
                password=None,
                elapsed_seconds=0.0,
                stats=self._stats,
                restore_token=None,
            )

        # Resolve the target entry and known plaintext. Prefer auto-detection
        # from a STORED entry's magic header; fall back to a user-supplied
        # plaintext_sample; otherwise skip.
        from uzpr.archive.detect import detect_archive
        from uzpr.archive.zip_inspect import find_known_plaintext_target, pick_attack_target

        archive_info = detect_archive(ctx.archive_path)
        auto_target = find_known_plaintext_target(archive_info)

        entry: str | None
        plain_path: Path | None

        if auto_target is not None:
            entry, magic_bytes = auto_target
            plain_path = ctx.work_dir / "known_plain.bin"
            plain_path.write_bytes(magic_bytes)
            sig = signature_for(entry)
            sig_name = sig.name if sig is not None else "unknown"
            await on_event(
                StageEvent(
                    ts=time.time(),
                    kind="log",
                    payload={"msg": f"Auto-detected known plaintext from {entry} ({sig_name})"},
                )
            )
        elif ctx.hints.plaintext_sample is not None:
            entry = pick_attack_target(archive_info)
            plain_path = ctx.hints.plaintext_sample
        else:
            log.debug("bkcrack_skip_no_plaintext")
            return StageResult(
                outcome=StageOutcome.SKIPPED,
                password=None,
                elapsed_seconds=time.monotonic() - start,
                stats=self._stats,
                restore_token=None,
            )

        if entry is None or plain_path is None:
            log.warning("bkcrack_no_attack_target", archive=str(ctx.archive_path))
            return StageResult(
                outcome=StageOutcome.SKIPPED,
                password=None,
                elapsed_seconds=time.monotonic() - start,
                stats=self._stats,
                restore_token=None,
            )

        binary = find_tool("bkcrack")
        runner = BkcrackRunner(binary, ctx.work_dir)
        self._active_runner = runner

        target_entry: str = entry
        target_plain: Path = plain_path
        result: StageResult | None = None

        async def _body() -> None:
            nonlocal result
            result = await _run_bkcrack(
                ctx=ctx,
                runner=runner,
                entry=target_entry,
                plain=target_plain,
                on_event=on_event,
                start_monotonic=start,
                stats=self._stats,
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
                    payload={"msg": "bkcrack budget exhausted, aborting"},
                )
            )
            return StageResult(
                outcome=StageOutcome.ABORTED,
                password=None,
                elapsed_seconds=elapsed,
                stats=self._stats,
                restore_token=None,
            )

        return result

    async def cancel(self) -> None:
        # BkcrackRunner does not expose a pause(); the underlying process will
        # be terminated when the anyio task group is cancelled.
        self._active_runner = None


async def _run_bkcrack(
    *,
    ctx: StageContext,
    runner: BkcrackRunner,
    entry: str,
    plain: Path,
    on_event: EventSink,
    start_monotonic: float,
    stats: StageStats,
) -> StageResult:
    """Execute the full bkcrack attack sequence and return a StageResult."""
    # Step 1: recover ZipCrypto internal keys
    keys = await runner.recover_keys(
        ctx.archive_path,
        entry,
        plain,
        on_event,
    )

    if keys is None:
        log.info("bkcrack_keys_not_recovered", archive=str(ctx.archive_path))
        return StageResult(
            outcome=StageOutcome.EXHAUSTED,
            password=None,
            elapsed_seconds=time.monotonic() - start_monotonic,
            stats=stats,
            restore_token=None,
        )

    stats.candidates_tested = 1

    # Step 2: decrypt the archive with the recovered keys
    out_path = ctx.work_dir / "decrypted.zip"
    try:
        await runner.decrypt(ctx.archive_path, keys, out_path)
        log.info("bkcrack_decrypted", out=str(out_path))
    except Exception as exc:
        log.warning("bkcrack_decrypt_failed", error=str(exc))
        # Decryption failure is non-fatal — we still have the keys

    # Step 3: optionally recover the original password string from the keys.
    # Reversing keys -> password is itself a brute force (bkcrack -r), only worth
    # attempting for SHORT passwords. The archive is already decrypted from the
    # keys, so the password string is cosmetic — we cap the attempt at length 7
    # to avoid wasting minutes on a long/random password we can never reverse.
    _PW_RECOVERY_MAX_LEN = 7
    password: str | None = None
    if ctx.hints.min_length <= _PW_RECOVERY_MAX_LEN:
        hi = min(ctx.hints.max_length, _PW_RECOVERY_MAX_LEN)
        password = await runner.recover_password(
            keys,
            (ctx.hints.min_length, hi),
            on_event,
        )

    # Build a stable keys-hex string regardless of whether password recovery succeeded
    keys_hex = " ".join(f"{k:08x}" for k in keys)

    if password is not None:
        log.info("bkcrack_password_recovered", password=password)
        reported_password = password
    else:
        # Signal to the caller that we have keys but no plaintext password
        reported_password = f"<keys-only:{keys_hex}>"
        log.info("bkcrack_keys_only", keys_hex=keys_hex)

    elapsed = time.monotonic() - start_monotonic
    return StageResult(
        outcome=StageOutcome.FOUND,
        password=reported_password,
        elapsed_seconds=elapsed,
        stats=stats,
        restore_token=None,
        error=None,
    )
