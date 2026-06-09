from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Awaitable, Callable, Protocol, runtime_checkable


class StageOutcome(str, Enum):
    FOUND = "found"
    EXHAUSTED = "exhausted"
    ABORTED = "aborted"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class Hints:
    full_password: str | None = None
    partial_mask: str | None = None
    dates: tuple[tuple[int, int, int], ...] = ()       # (d, m, y)
    first_names: tuple[str, ...] = ()
    surnames: tuple[str, ...] = ()
    nicknames: tuple[str, ...] = ()
    pet_names: tuple[str, ...] = ()
    places: tuple[str, ...] = ()
    stems: tuple[str, ...] = ()
    suffixes: tuple[str, ...] = ()
    prefixes: tuple[str, ...] = ()
    case_styles: tuple[str, ...] = ()
    must_have: frozenset[str] = frozenset()
    min_length: int = 6
    max_length: int = 16
    locale: str = "en-GB"
    plaintext_sample: Path | None = None


@dataclass(frozen=True, slots=True)
class StageContext:
    session_id: str
    stage_id: str
    stage_no: int
    archive_path: Path
    hash_file: Path
    archive_format: str            # 'zip-classic'|'zip-aes'|'rar3'|'rar5'
    hashcat_mode: int | None       # 17200/17225/13600/12500/13000/None
    hints: Hints
    budget_seconds: float
    work_dir: Path
    shared_potfile: Path
    tried_candidates_db: Path
    gpu_devices: tuple[int, ...]
    low_power: bool
    restore_token: str | None = None


@dataclass(slots=True)
class StagePlan:
    estimated_keyspace: int
    estimated_candidates_per_sec: float
    prior_probability: float
    requires_gpu: bool
    can_resume: bool


@dataclass(slots=True)
class StageStats:
    candidates_tested: int = 0
    peak_candidates_per_sec: float = 0.0
    avg_candidates_per_sec: float = 0.0
    gpu_peak_temp_c: float | None = None
    rejected_candidates: int = 0


@dataclass(slots=True)
class StageResult:
    outcome: StageOutcome
    password: str | None
    elapsed_seconds: float
    stats: StageStats
    restore_token: str | None
    error: str | None = None


@dataclass(slots=True)
class StageEvent:
    ts: float
    kind: str                      # 'progress'|'rate'|'sample'|'log'
    payload: dict[str, object] = field(default_factory=dict)


EventSink = Callable[[StageEvent], Awaitable[None]]


@runtime_checkable
class Stage(Protocol):
    stage_no: int
    name: str
    engine: str                    # 'native'|'hashcat'|'john'|'bkcrack'

    async def prepare(self, ctx: StageContext) -> StagePlan: ...
    async def run(self, ctx: StageContext, on_event: EventSink) -> StageResult: ...
    async def cancel(self) -> None: ...
