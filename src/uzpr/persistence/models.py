from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SessionRow:
    id: str
    archive_path: str
    archive_sha256: str
    archive_format: str
    hashcat_mode: int | None
    total_budget_s: float
    hints_json: bytes
    status: str
    gpu_low_power: int
    created_at: float
    updated_at: float


@dataclass(slots=True)
class StageRow:
    id: str
    session_id: str
    stage_no: int
    name: str
    engine: str
    status: str
    budget_s: float
    prior_p: float
    candidates_tested: int
    elapsed_s: float
    restore_token: str | None
    last_heartbeat_at: float | None
    failure_count: int


@dataclass(slots=True)
class AttemptRow:
    id: int
    session_id: str
    stage_id: str
    started_at: float
    ended_at: float | None
    outcome: str | None
    candidates_tested: int
    peak_rate: float | None


@dataclass(slots=True)
class ResultRow:
    session_id: str
    password: str
    found_by_stage_id: str
    found_at: float
    bkcrack_keys: str | None


@dataclass(slots=True)
class EventRow:
    id: int
    session_id: str
    stage_id: str | None
    ts: float
    level: str
    payload_json: str


@dataclass(slots=True)
class CapabilityCacheRow:
    device_key: str
    device_name: str
    driver_version: str
    benchmarks_json: str
    probed_at: float
