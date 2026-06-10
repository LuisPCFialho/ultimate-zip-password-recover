from __future__ import annotations

import time
from pathlib import Path

from uzpr.core.budget import BudgetAllocator
from uzpr.core.capability import CapabilityProbe
from uzpr.core.hints import deserialize_hints
from uzpr.core.stages.protocol import (
    EventSink,
    Hints,
    Stage,
    StageContext,
    StageOutcome,
    StagePlan,
    StageResult,
    StageStats,
)
from uzpr.persistence.encryption import dpapi_decrypt
from uzpr.persistence.repo import SessionRepo
from uzpr.util.logging import get_logger
from uzpr.util.paths import session_work_dir

log = get_logger(__name__)


def _yield_density(plan: StagePlan) -> float:
    """Probability-of-finding per second-of-work. Higher = schedule earlier."""
    expected_seconds = plan.estimated_keyspace / max(plan.estimated_candidates_per_sec, 1.0)
    return plan.prior_probability / max(expected_seconds, 0.001)


def _sort_by_ev(
    prepared: dict[int, StagePlan],
    stages: tuple[Stage, ...],
    gpu_available: bool,
) -> list[Stage]:
    """Order *stages* (those present in *prepared*) by descending yield density.

    Stages that require a GPU when none is available are deprioritized to the end.
    Stages absent from *prepared* (zero prior or already done) are excluded.
    """
    eligible = [s for s in stages if s.stage_no in prepared]
    if not eligible:
        return []

    def sort_key(stage: Stage) -> tuple[int, float]:
        plan = prepared[stage.stage_no]
        gpu_penalty = 1 if (plan.requires_gpu and not gpu_available) else 0
        # Negative density so higher density sorts first within each gpu_penalty bucket.
        return (gpu_penalty, -_yield_density(plan))

    return sorted(eligible, key=sort_key)


class Orchestrator:
    """Cascade session orchestrator: drives stages 1–13 in order, manages budget
    redistribution, pause/resume/cancel, and persistence of all state."""

    def __init__(
        self,
        repo: SessionRepo,
        capability: CapabilityProbe,
        stages: tuple[Stage, ...],
    ) -> None:
        self._repo = repo
        self._capability = capability
        self._stages = stages
        self._active_stages: dict[str, Stage] = {}
        # Sessions the user explicitly paused/cancelled. Used to distinguish a
        # genuine user-initiated ABORT from a per-stage budget timeout (which
        # should let the cascade continue to the next stage).
        self._user_stopped: set[str] = set()

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def run_session(self, session_id: str, on_event: EventSink) -> StageResult:
        """Drive all cascade stages for *session_id*, emitting events via *on_event*."""
        self._user_stopped.discard(session_id)
        session = await self._repo.get_session(session_id)
        stage_rows = await self._repo.list_stages(session_id)

        # Build a map of stage_no → StageRow for fast lookup.
        row_by_no = {r.stage_no: r for r in stage_rows}

        # Detect GPUs (updates internal capability state).
        await self._capability.detect_gpus()

        allocator = BudgetAllocator(total_budget_s=session.total_budget_s)

        # Decode hints once.
        hints: Hints = deserialize_hints(dpapi_decrypt(session.hints_json))

        work_dir = session_work_dir(session_id)
        shared_potfile = work_dir / "uzpr.pot"
        tried_candidates_db = work_dir / "tried.db"

        # Locate (or derive) the hash file once up-front (shared by all stages).
        archive_path = Path(session.archive_path)
        hash_file = work_dir / f"{archive_path.stem}.hash"
        if not hash_file.exists():
            hash_file = await self._extract_hash(archive_path, work_dir)

        # Compute hashcat mode once up-front.
        hashcat_mode = session.hashcat_mode
        if hashcat_mode is None and hash_file.exists() and hash_file.stat().st_size > 0:
            try:
                from uzpr.archive.detect import detect_archive
                from uzpr.archive.hashcat_mode import hashcat_mode_for

                archive_info = detect_archive(archive_path)
                hashcat_mode = hashcat_mode_for(archive_info, hash_file)
                if hashcat_mode is not None:
                    await self._repo.update_session_hashcat_mode(session_id, hashcat_mode)
                    log.info("hashcat_mode_detected", mode=hashcat_mode, session_id=session_id)
            except Exception as exc:
                log.warning("hashcat_mode_detection_failed", error=str(exc))

        # Build a probe context (budget=0 here; real budget is set per-run below).
        def _make_ctx(stage: Stage, stage_id: str, restore_token: str | None, budget: float) -> StageContext:
            return StageContext(
                session_id=session_id,
                stage_id=stage_id,
                stage_no=stage.stage_no,
                archive_path=archive_path,
                hash_file=hash_file,
                archive_format=session.archive_format,
                hashcat_mode=hashcat_mode,
                hints=hints,
                budget_seconds=budget,
                work_dir=work_dir,
                shared_potfile=shared_potfile,
                tried_candidates_db=tried_candidates_db,
                gpu_devices=self._capability.get_gpu_ids(),
                low_power=bool(session.gpu_low_power),
                restore_token=restore_token,
            )

        # Identify pending stages (not yet finished per DB).
        pending: list[Stage] = []
        stage_ids: dict[int, str] = {}
        restore_tokens: dict[int, str | None] = {}
        for stage in self._stages:
            row = row_by_no.get(stage.stage_no)
            if row is not None and row.status in ("found", "exhausted", "skipped"):
                log.debug(
                    "stage_skipped_already_done",
                    session_id=session_id,
                    stage_no=stage.stage_no,
                    status=row.status,
                )
                continue
            pending.append(stage)
            stage_ids[stage.stage_no] = (
                f"{session_id}_{stage.stage_no}" if row is None else row.id
            )
            restore_tokens[stage.stage_no] = row.restore_token if row is not None else None

        # First pass: prepare every pending stage with a probe context to obtain
        # its keyspace/cps/prior estimates.
        prepared: dict[int, StagePlan] = {}
        for stage in pending:
            probe_ctx = _make_ctx(stage, stage_ids[stage.stage_no], restore_tokens[stage.stage_no], 0.0)
            plan = await stage.prepare(probe_ctx)
            if plan.prior_probability == 0.0:
                log.info(
                    "stage_skipped_zero_prior",
                    session_id=session_id,
                    stage_no=stage.stage_no,
                    name=stage.name,
                )
                await self._repo.update_stage(stage_ids[stage.stage_no], status="skipped")
                continue
            prepared[stage.stage_no] = plan

        # Sort by EV yield density. Fall back to numeric order if nothing eligible.
        gpu_available = bool(self._capability.get_gpu_ids())
        ordered = _sort_by_ev(prepared, tuple(pending), gpu_available)
        if not ordered:
            ordered = list(pending)

        log.info(
            "ev_schedule",
            session_id=session_id,
            order=[
                (s.stage_no, round(_yield_density(prepared[s.stage_no]), 6))
                for s in ordered
                if s.stage_no in prepared
            ],
        )

        remaining_stage_nos = [s.stage_no for s in ordered if s.stage_no in prepared]

        for stage in ordered:
            # Skip stages that were filtered out by zero-prior in the prepare pass.
            if stage.stage_no not in prepared:
                continue

            # Allocate budget for all still-remaining stages.
            budget_map = allocator.allocate(remaining_stage_nos)
            budget = budget_map.get(stage.stage_no, 0.0)

            stage_id = stage_ids[stage.stage_no]
            restore_token = restore_tokens[stage.stage_no]
            ctx = _make_ctx(stage, stage_id, restore_token, budget)

            # Mark running.
            await self._repo.update_stage(
                stage_id,
                status="running",
                last_heartbeat_at=time.time(),
            )
            self._active_stages[session_id] = stage

            started_at = time.time()
            log.info(
                "stage_start",
                session_id=session_id,
                stage_no=stage.stage_no,
                name=stage.name,
                budget_s=budget,
            )

            try:
                result = await stage.run(ctx, on_event)
            except Exception as exc:
                elapsed = time.time() - started_at
                log.error(
                    "stage_exception",
                    session_id=session_id,
                    stage_no=stage.stage_no,
                    error=str(exc),
                    exc_info=True,
                )
                result = StageResult(
                    outcome=StageOutcome.FAILED,
                    password=None,
                    elapsed_seconds=elapsed,
                    stats=StageStats(),
                    restore_token=None,
                    error=str(exc),
                )
            finally:
                self._active_stages.pop(session_id, None)

            elapsed = time.time() - started_at

            # Persist stage outcome.
            await self._repo.update_stage(
                stage_id,
                status=result.outcome.value,
                elapsed_s=elapsed,
                candidates_tested=result.stats.candidates_tested,
                restore_token=result.restore_token,
                last_heartbeat_at=time.time(),
            )

            # Record attempt row.
            await self._repo.record_attempt(
                stage_id=stage_id,
                started_at=started_at,
                ended_at=time.time(),
                outcome=result.outcome.value,
                candidates=result.stats.candidates_tested,
                peak_rate=result.stats.peak_candidates_per_sec or None,
            )

            log.info(
                "stage_complete",
                session_id=session_id,
                stage_no=stage.stage_no,
                outcome=result.outcome.value,
                elapsed_s=elapsed,
                candidates=result.stats.candidates_tested,
            )

            if result.outcome == StageOutcome.FOUND:
                assert result.password is not None
                await self._repo.record_result(
                    session_id=session_id,
                    password=result.password,
                    stage_id=stage_id,
                )
                await self._repo.update_session_status(session_id, "found")
                return result

            if result.outcome == StageOutcome.ABORTED:
                if session_id in self._user_stopped:
                    # Genuine user-initiated pause/cancel — stop the cascade.
                    await self._repo.update_session_status(session_id, "paused")
                    return result
                # Per-stage budget timeout — treat like EXHAUSTED and continue
                # to the next stage in the cascade.
                log.info(
                    "stage_budget_timeout_continuing",
                    session_id=session_id,
                    stage_no=stage.stage_no,
                    elapsed_s=elapsed,
                )
                # Debit the time this stage actually consumed.
                allocator.consume(stage.stage_no, elapsed)
                remaining_stage_nos = [n for n in remaining_stage_nos if n != stage.stage_no]
                continue

            if result.outcome == StageOutcome.FAILED:
                log.warning(
                    "stage_failed_continuing",
                    session_id=session_id,
                    stage_no=stage.stage_no,
                    error=result.error,
                )
                # Do not return unused budget to the pool for FAILED stages —
                # the stage may have consumed part of it before crashing.
                remaining_stage_nos = [n for n in remaining_stage_nos if n != stage.stage_no]
                continue

            # EXHAUSTED — debit the time this stage actually consumed.
            allocator.consume(stage.stage_no, elapsed)
            remaining_stage_nos = [n for n in remaining_stage_nos if n != stage.stage_no]

        # All stages done without finding the password.
        await self._repo.update_session_status(session_id, "exhausted")
        log.info("session_exhausted", session_id=session_id)
        return StageResult(
            outcome=StageOutcome.EXHAUSTED,
            password=None,
            elapsed_seconds=0.0,
            stats=StageStats(),
            restore_token=None,
        )

    async def pause(self, session_id: str) -> None:
        """Request the currently-running stage for *session_id* to stop."""
        self._user_stopped.add(session_id)
        stage = self._active_stages.get(session_id)
        if stage is not None:
            await stage.cancel()

    async def resume(self, session_id: str, on_event: EventSink) -> StageResult:
        """Resume a paused session by re-entering the cascade loop.

        ``run_session`` already skips stages whose DB status is 'found',
        'exhausted', or 'skipped', so this is a straight delegation.
        """
        self._user_stopped.discard(session_id)
        return await self.run_session(session_id, on_event)

    async def cancel(self, session_id: str) -> None:
        """Pause the running stage then mark the session as failed."""
        await self.pause(session_id)
        await self._repo.update_session_status(session_id, "failed")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _extract_hash(self, archive_path: Path, work_dir: Path) -> Path:
        """Run zip2john / rar2john to produce the hash file, returning its path."""
        from uzpr.engines.tool_manager import ToolNotFoundError, find_tool

        stem = archive_path.stem
        hash_file = work_dir / f"{stem}.hash"
        suffix = archive_path.suffix.lower()

        tool_name = "zip2john" if suffix in (".zip",) else "rar2john"

        try:
            tool = find_tool(tool_name)  # type: ignore[arg-type]
        except ToolNotFoundError:
            log.warning("hash_extraction_tool_missing", tool=tool_name, archive=str(archive_path))
            # Return the path even if empty; the stage will handle the missing file.
            return hash_file

        import anyio

        try:
            result = await anyio.run_process(
                [str(tool), str(archive_path)],
                check=False,
            )
            raw = result.stdout.decode(errors="replace")
            # zip2john / rar2john output lines are: filename:HASH[:extra:fields]
            # hashcat only accepts the HASH part — strip prefix and trailing fields.
            cleaned_lines = []
            for line in raw.splitlines():
                line = line.strip()
                if not line or ":" not in line:
                    continue
                parts = line.split(":", 1)
                if len(parts) < 2:
                    continue
                hash_part = parts[1]
                # For $zip2$: the hash ends at *$/zip2$, strip trailing fields
                if "$zip2$" in hash_part:
                    end = hash_part.find("*$/zip2$")
                    if end != -1:
                        hash_part = hash_part[: end + 8]
                # For $pkzip2$ or $pkzip$: the hash is self-contained, strip trailing :fields
                elif "$pkzip" in hash_part:
                    # Find the closing $*/pkzip2$ marker or $*/pkzip$
                    for marker in ("*$/pkzip2$", "*$/pkzip$"):
                        end = hash_part.find(marker)
                        if end != -1:
                            hash_part = hash_part[: end + len(marker)]
                            break
                # For RAR: $RAR3$ and $rar5$ are already clean
                if hash_part.startswith("$"):
                    cleaned_lines.append(hash_part)
            if cleaned_lines:
                hash_file.write_text("\n".join(cleaned_lines) + "\n", encoding="utf-8")
            else:
                # Fallback: write raw and let hashcat try
                hash_file.write_bytes(result.stdout)
            log.info(
                "hash_extracted",
                archive=str(archive_path),
                hash_file=str(hash_file),
                lines=len(cleaned_lines),
            )
        except Exception as exc:
            log.error("hash_extraction_failed", archive=str(archive_path), error=str(exc))

        return hash_file
