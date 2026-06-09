from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

import anyio.to_thread

from uzpr.core.hints import Hints, serialize_hints
from uzpr.persistence.encryption import dpapi_encrypt
from uzpr.persistence.models import (
    SessionRow,
    StageRow,
)

# (stage_no, name, engine, prior_p, budget_fraction)
# budget_fraction: 0 means free/zero-cost stage; positive fractions must sum to 1.0
# Stages 4-12 split the paid time pool equally (9 stages, each gets 1/9).
_STAGE_DEFAULTS: tuple[tuple[int, str, str, float, float], ...] = (
    (1, "known-password", "native", 1.0, 0.0),
    (2, "partial-mask", "hashcat", 0.7, 0.0),
    (3, "generated-wordlist", "hashcat", 0.4, 0.0),
    (4, "rockyou-straight", "hashcat", 0.35, 1 / 9),
    (5, "rockyou-rules", "hashcat", 0.30, 1 / 9),
    (6, "masks-brute", "hashcat", 0.25, 1 / 9),
    (7, "prince-stems", "hashcat", 0.20, 1 / 9),
    (8, "john-incremental", "john", 0.15, 1 / 9),
    (9, "hybrid-wl-mask", "hashcat", 0.12, 1 / 9),
    (10, "hybrid-mask-wl", "hashcat", 0.10, 1 / 9),
    (11, "combinator", "hashcat", 0.08, 1 / 9),
    (12, "targeted-brute", "hashcat", 0.06, 1 / 9),
    (13, "bkcrack-plaintext", "bkcrack", 1.0, 0.0),
)


def _row_to_session(row: sqlite3.Row) -> SessionRow:
    return SessionRow(
        id=row["id"],
        archive_path=row["archive_path"],
        archive_sha256=row["archive_sha256"],
        archive_format=row["archive_format"],
        hashcat_mode=row["hashcat_mode"],
        total_budget_s=row["total_budget_s"],
        hints_json=row["hints_json"],
        status=row["status"],
        gpu_low_power=row["gpu_low_power"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_stage(row: sqlite3.Row) -> StageRow:
    return StageRow(
        id=row["id"],
        session_id=row["session_id"],
        stage_no=row["stage_no"],
        name=row["name"],
        engine=row["engine"],
        status=row["status"],
        budget_s=row["budget_s"],
        prior_p=row["prior_p"],
        candidates_tested=row["candidates_tested"],
        elapsed_s=row["elapsed_s"],
        restore_token=row["restore_token"],
        last_heartbeat_at=row["last_heartbeat_at"],
        failure_count=row["failure_count"],
    )


class SessionRepo:
    def __init__(self, db_path: Path, dpapi_key: bytes = b"") -> None:
        self._db_path = db_path
        self._dpapi_key = dpapi_key
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = self._open_connection()
        self._apply_migrations()

    # ------------------------------------------------------------------
    # Internal helpers (called from thread via anyio)
    # ------------------------------------------------------------------

    def _open_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _apply_migrations(self) -> None:
        conn = self._conn
        conn.execute("CREATE TABLE IF NOT EXISTS schema_versions (filename TEXT PRIMARY KEY)")
        conn.commit()
        migrations_dir = Path(__file__).parent / "migrations"
        sql_files = sorted(migrations_dir.glob("*.sql"))
        for sql_file in sql_files:
            filename = sql_file.name
            already_applied = conn.execute(
                "SELECT 1 FROM schema_versions WHERE filename = ?", (filename,)
            ).fetchone()
            if already_applied:
                continue
            sql = sql_file.read_text(encoding="utf-8")
            # PRAGMAs cannot run inside a transaction; execute them separately.
            pragma_lines: list[str] = []
            statement_lines: list[str] = []
            for line in sql.splitlines():
                stripped = line.strip()
                if stripped.upper().startswith("PRAGMA"):
                    pragma_lines.append(stripped)
                else:
                    statement_lines.append(line)
            for pragma in pragma_lines:
                conn.execute(pragma)
            conn.executescript("\n".join(statement_lines))
            conn.execute("INSERT INTO schema_versions (filename) VALUES (?)", (filename,))
            conn.commit()

    # ------------------------------------------------------------------
    # Sync implementations (run in a thread)
    # ------------------------------------------------------------------

    def _sync_create_session(
        self,
        archive_info: Any,
        hints: Hints,
        total_budget_s: float,
        gpu_low_power: bool,
    ) -> str:
        session_id = str(uuid.uuid4())
        now = time.time()
        hints_blob = dpapi_encrypt(serialize_hints(hints))
        conn = self._conn
        conn.execute(
            """
            INSERT INTO sessions
                (id, archive_path, archive_sha256, archive_format, hashcat_mode,
                 total_budget_s, hints_json, status, gpu_low_power, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (
                session_id,
                str(archive_info.path),
                archive_info.path.name,  # sha256 placeholder; caller should set via update
                archive_info.format,
                getattr(archive_info, "hashcat_mode", None),
                total_budget_s,
                hints_blob,
                1 if gpu_low_power else 0,
                now,
                now,
            ),
        )
        # Create stage rows
        paid_budget_total = total_budget_s  # paid stages share the full budget
        for stage_no, name, engine, prior_p, budget_fraction in _STAGE_DEFAULTS:
            stage_id = str(uuid.uuid4())
            budget_s = paid_budget_total * budget_fraction if budget_fraction > 0.0 else 0.0
            conn.execute(
                """
                INSERT INTO stages
                    (id, session_id, stage_no, name, engine, status,
                     budget_s, prior_p, candidates_tested, elapsed_s,
                     restore_token, last_heartbeat_at, failure_count)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, 0, 0, NULL, NULL, 0)
                """,
                (stage_id, session_id, stage_no, name, engine, budget_s, prior_p),
            )
        conn.commit()
        return session_id

    def _sync_get_session(self, session_id: str) -> SessionRow:
        row = self._conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise KeyError(f"Session not found: {session_id}")
        return _row_to_session(row)

    def _sync_list_sessions(self, status: str | None) -> list[SessionRow]:
        if status is None:
            rows = self._conn.execute("SELECT * FROM sessions").fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM sessions WHERE status = ?", (status,)
            ).fetchall()
        return [_row_to_session(r) for r in rows]

    def _sync_list_stages(self, session_id: str) -> list[StageRow]:
        rows = self._conn.execute(
            "SELECT * FROM stages WHERE session_id = ? ORDER BY stage_no",
            (session_id,),
        ).fetchall()
        return [_row_to_stage(r) for r in rows]

    def _sync_update_session_status(self, session_id: str, status: str) -> None:
        now = time.time()
        self._conn.execute(
            "UPDATE sessions SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, session_id),
        )
        self._conn.commit()

    def _sync_update_stage(self, stage_id: str, fields: dict[str, object]) -> None:
        if not fields:
            return
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = [*list(fields.values()), stage_id]
        self._conn.execute(f"UPDATE stages SET {set_clause} WHERE id = ?", values)
        self._conn.commit()

    def _sync_record_attempt(
        self,
        stage_id: str,
        started_at: float,
        ended_at: float,
        outcome: str,
        candidates: int,
        peak_rate: float | None,
    ) -> None:
        stage_row = self._conn.execute(
            "SELECT session_id FROM stages WHERE id = ?", (stage_id,)
        ).fetchone()
        if stage_row is None:
            raise KeyError(f"Stage not found: {stage_id}")
        self._conn.execute(
            """
            INSERT INTO attempts
                (session_id, stage_id, started_at, ended_at,
                 outcome, candidates_tested, peak_rate)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stage_row["session_id"],
                stage_id,
                started_at,
                ended_at,
                outcome,
                candidates,
                peak_rate,
            ),
        )
        self._conn.commit()

    def _sync_record_result(
        self,
        session_id: str,
        password: str,
        stage_id: str,
        bkcrack_keys: str | None,
    ) -> None:
        now = time.time()
        self._conn.execute(
            """
            INSERT INTO results
                (session_id, password, found_by_stage_id, found_at, bkcrack_keys)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, password, stage_id, now, bkcrack_keys),
        )
        self._conn.execute(
            "UPDATE sessions SET status = 'found', updated_at = ? WHERE id = ?",
            (now, session_id),
        )
        self._conn.commit()

    def _sync_append_event(
        self,
        session_id: str,
        stage_id: str | None,
        level: str,
        payload: dict[str, object],
    ) -> None:
        now = time.time()
        self._conn.execute(
            """
            INSERT INTO events (session_id, stage_id, ts, level, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, stage_id, now, level, json.dumps(payload)),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def create_session(
        self,
        archive_info: Any,
        hints: Hints,
        total_budget_s: float,
        gpu_low_power: bool,
    ) -> str:
        return await anyio.to_thread.run_sync(
            lambda: self._sync_create_session(archive_info, hints, total_budget_s, gpu_low_power)
        )

    async def get_session(self, session_id: str) -> SessionRow:
        return await anyio.to_thread.run_sync(lambda: self._sync_get_session(session_id))

    async def list_sessions(self, status: str | None = None) -> list[SessionRow]:
        return await anyio.to_thread.run_sync(lambda: self._sync_list_sessions(status))

    async def list_stages(self, session_id: str) -> list[StageRow]:
        return await anyio.to_thread.run_sync(lambda: self._sync_list_stages(session_id))

    async def update_session_status(self, session_id: str, status: str) -> None:
        await anyio.to_thread.run_sync(lambda: self._sync_update_session_status(session_id, status))

    async def update_session_hashcat_mode(self, session_id: str, mode: int) -> None:
        """Persist the detected hashcat mode after hash extraction."""
        await anyio.to_thread.run_sync(
            lambda: (
                self._conn.execute(
                    "UPDATE sessions SET hashcat_mode = ?, updated_at = ? WHERE id = ?",
                    (mode, __import__("time").time(), session_id),
                )
                or self._conn.commit()
            )
        )

    async def update_stage(self, stage_id: str, **fields: object) -> None:
        await anyio.to_thread.run_sync(lambda: self._sync_update_stage(stage_id, dict(fields)))

    async def record_attempt(
        self,
        stage_id: str,
        started_at: float,
        ended_at: float,
        outcome: str,
        candidates: int,
        peak_rate: float | None,
    ) -> None:
        await anyio.to_thread.run_sync(
            lambda: self._sync_record_attempt(
                stage_id, started_at, ended_at, outcome, candidates, peak_rate
            )
        )

    async def record_result(
        self,
        session_id: str,
        password: str,
        stage_id: str,
        bkcrack_keys: str | None = None,
    ) -> None:
        await anyio.to_thread.run_sync(
            lambda: self._sync_record_result(session_id, password, stage_id, bkcrack_keys)
        )

    async def append_event(
        self,
        session_id: str,
        stage_id: str | None,
        level: str,
        payload: dict[str, object],
    ) -> None:
        await anyio.to_thread.run_sync(
            lambda: self._sync_append_event(session_id, stage_id, level, payload)
        )
