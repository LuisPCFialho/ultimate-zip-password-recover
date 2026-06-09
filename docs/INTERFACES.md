# UZPR Build Interfaces (read this before writing any module)

Self-contained interface reference for build agents. The full architecture is in
`ARCHITECTURE.md`; this file extracts every type signature, SQL schema, and
command template that cross-module code depends on. **Implementations must
match these signatures byte-for-byte.**

---

## 1. The Stage protocol (src/uzpr/core/stages/protocol.py)

```python
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
```

---

## 2. SQLite schema (src/uzpr/persistence/migrations/0001_init.sql)

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA wal_autocheckpoint = 1000;

CREATE TABLE sessions (
    id              TEXT PRIMARY KEY,
    archive_path    TEXT NOT NULL,
    archive_sha256  TEXT NOT NULL,
    archive_format  TEXT NOT NULL,
    hashcat_mode    INTEGER,
    total_budget_s  REAL NOT NULL,
    hints_json      BLOB NOT NULL,
    status          TEXT NOT NULL,
    gpu_low_power   INTEGER NOT NULL DEFAULT 0,
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
);
CREATE INDEX idx_sessions_archive ON sessions(archive_sha256);
CREATE INDEX idx_sessions_status ON sessions(status);

CREATE TABLE stages (
    id                  TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    stage_no            INTEGER NOT NULL,
    name                TEXT NOT NULL,
    engine              TEXT NOT NULL,
    status              TEXT NOT NULL,
    budget_s            REAL NOT NULL,
    prior_p             REAL NOT NULL,
    candidates_tested   INTEGER NOT NULL DEFAULT 0,
    elapsed_s           REAL NOT NULL DEFAULT 0,
    restore_token       TEXT,
    last_heartbeat_at   REAL,
    failure_count       INTEGER NOT NULL DEFAULT 0,
    UNIQUE(session_id, stage_no)
);
CREATE INDEX idx_stages_status ON stages(status);

CREATE TABLE attempts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    stage_id            TEXT NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
    started_at          REAL NOT NULL,
    ended_at            REAL,
    outcome             TEXT,
    candidates_tested   INTEGER NOT NULL DEFAULT 0,
    peak_rate           REAL
);
CREATE INDEX idx_attempts_session ON attempts(session_id);

CREATE TABLE results (
    session_id          TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    password            TEXT NOT NULL,
    found_by_stage_id   TEXT NOT NULL REFERENCES stages(id),
    found_at            REAL NOT NULL,
    bkcrack_keys        TEXT
);

CREATE TABLE events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    stage_id            TEXT REFERENCES stages(id) ON DELETE CASCADE,
    ts                  REAL NOT NULL,
    level               TEXT NOT NULL,
    payload_json        TEXT NOT NULL
);
CREATE INDEX idx_events_session_ts ON events(session_id, ts);

CREATE TABLE tried_candidates (
    hash_blake3         BLOB PRIMARY KEY,
    first_seen_stage    INTEGER NOT NULL,
    ts                  REAL NOT NULL
) WITHOUT ROWID;

CREATE TABLE capability_cache (
    device_key          TEXT PRIMARY KEY,
    device_name         TEXT NOT NULL,
    driver_version      TEXT NOT NULL,
    benchmarks_json     TEXT NOT NULL,
    probed_at           REAL NOT NULL
);
```

Storage: `%LOCALAPPDATA%\UltimateZipPasswordRecover\uzpr.db`.

---

## 3. Archive detection — supported formats

| `archive_format` string | Detection                                                       | hashcat mode | john format    |
|-------------------------|-----------------------------------------------------------------|--------------|----------------|
| `zip-classic`           | `PK\x03\x04`, GP bit 0=1, method != 99                          | 17200/17210/17220/17225/17230 | zip            |
| `zip-aes`               | `PK\x03\x04`, method == 99, extra field 0x9901, vendor `AE`     | 13600        | zip-aes        |
| `rar3-hp`               | `Rar!\x1a\x07\x00`, header encrypted (`-hp`)                    | 12500        | rar            |
| `rar5`                  | `Rar!\x1a\x07\x01\x00`                                          | 13000        | rar5           |
| `pkware-strong`         | GP bit 6=1 (strong) — **detected but refused**                  | —            | —              |
| `plain`                 | GP bit 0=0 — refuse                                             | —            | —              |
| `unsupported`           | anything else                                                   | —            | —              |

zip2john tag → hashcat mode mapping:

| zip2john output prefix             | hashcat mode |
|------------------------------------|--------------|
| `$pkzip$1*...*CT=0`                | 17210        |
| `$pkzip$1*...*CT=8`                | 17200        |
| `$pkzip2$3*...` (mixed CT)         | 17225        |
| `$pkzip2$3*...` (all CT=8)         | 17220        |
| `$pkzip2$8*...`                    | 17230        |
| `$zip$2*...` (AES)                 | 13600        |
| `$zip3$...`                        | pkware-strong (refuse) |

---

## 4. External binaries — bundled paths and command templates

All binaries are invoked by **absolute path** under `<install>/tools/<tool>/`, `shell=False`.

### hashcat

Common flags: `--quiet --status --status-json --status-timer=2 --session=<sess> --restore-file-path=<work>/<sess>.restore --potfile-path=<work>/uzpr.pot --outfile=<work>/<sess>.out --outfile-format=2 -O -w 2 -d <gpu_ids>`.

Low-power mode adds: `-w 1 --hwmon-temp-abort=75 --gpu-temp-retain=70`.

Pause: write `q\n` to stdin; SIGTERM at `status-timer+5s`; SIGKILL at +10s more.
Resume: `hashcat.exe --session=<sess> --restore --restore-file-path=<work>`.
Capability probe: `hashcat.exe -b -m <mode> -d <id> --runtime=10 -O -w 2 --machine-readable`.

### john

Common: `--session=<sess> --pot=<work>/uzpr.pot --format=<zip|zip-aes|rar|rar5>`, cwd=`<install>/tools/john/run`, `creationflags=CREATE_NEW_PROCESS_GROUP` on Windows.

- Dictionary: `john.exe --session=<s> --pot=<p> --format=<f> --wordlist=<w> <hashfile>`
- Jumbo rules: as above + `--rules=jumbo`
- Status poll: `john.exe --status=<s>` parsed `r'(\d+)g\s+\S+\s+([0-9.]+)%.*\s+(\d+)p/s'`
- Pause: `GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT, pid)`
- Resume: `john.exe --restore=<s>`

Hash extraction:

```
zip2john.exe <archive.zip> > <work>/<archive>.hash
rar2john.exe <archive.rar> > <work>/<archive>.hash
```

### bkcrack (Stage 13 only, ZipCrypto, needs plaintext sample)

```
bkcrack.exe -L <target.zip>
bkcrack.exe -C <target.zip> -c <entry> -P <plain.zip> -p <entry>
bkcrack.exe -C <target.zip> -c <entry> -k K1 K2 K3 -D <decrypted.zip>
bkcrack.exe -k K1 K2 K3 -r 8..12 ?p   # optional password recovery
```

---

## 5. Cross-module function signatures

### archive package

```python
def detect_archive(path: Path) -> ArchiveInfo: ...
def extract_hash(info: ArchiveInfo, work_dir: Path) -> Path: ...        # returns hash file
def pick_attack_target(info: ArchiveInfo) -> str | None: ...             # entry name for bkcrack
def hashcat_mode_for(info: ArchiveInfo, hash_file: Path) -> int | None: ...

@dataclass(frozen=True, slots=True)
class ArchiveInfo:
    path: Path
    format: str                  # 'zip-classic'|'zip-aes'|'rar3-hp'|'rar5'|'pkware-strong'|'plain'|'unsupported'
    entries: tuple[ZipEntry | RarEntry, ...]
    aes_strength: int | None     # 128|192|256 if zip-aes
    header_encrypted: bool       # rar3 -hp
```

### wordlist package

```python
async def generate(hints: Hints, work_dir: Path, cap: int = 10_000_000) -> Path: ...     # writes stage3.wordlist, returns path
def estimate_count(hints: Hints) -> int: ...                                              # cheap upper bound for UI
def derive_masks(hints: Hints, max_masks: int = 200) -> Path: ...                         # writes .hcmask file, returns path
def build_prince_elements(stems: list[str], top_dict: Path, out: Path) -> None: ...
def encode_dates(dates: tuple[tuple[int, int, int], ...], locale: str) -> list[str]: ...  # 40 variants per date
```

### engines package

```python
class HashcatRunner:
    def __init__(self, binary: Path, work_dir: Path): ...
    async def run(self, mode: int, attack: int, hash_file: Path, *args: str,
                  potfile: Path, session: str, on_event: EventSink) -> StageResult: ...
    async def pause(self) -> None: ...
    async def resume(self, session: str) -> None: ...
    async def benchmark(self, mode: int, device_id: int) -> float: ...   # H/s

class JohnRunner:
    def __init__(self, binary: Path, work_dir: Path): ...
    async def run(self, fmt: str, hash_file: Path, *args: str,
                  potfile: Path, session: str, on_event: EventSink) -> StageResult: ...
    async def pause(self) -> None: ...
    async def resume(self, session: str) -> None: ...

class BkcrackRunner:
    def __init__(self, binary: Path, work_dir: Path): ...
    async def recover_keys(self, archive: Path, entry: str, plain: Path,
                           on_event: EventSink) -> tuple[int, int, int] | None: ...
    async def decrypt(self, archive: Path, keys: tuple[int, int, int], out: Path) -> None: ...
    async def recover_password(self, keys: tuple[int, int, int], length_range: tuple[int, int],
                               on_event: EventSink) -> str | None: ...

class NativeVerifier:
    def __init__(self, archive: Path, fmt: str): ...
    async def verify(self, candidate: str) -> bool: ...
    async def verify_batch(self, candidates: list[str]) -> str | None: ...
```

### persistence package

```python
class SessionRepo:
    def __init__(self, db_path: Path, dpapi_key: bytes): ...
    async def create_session(self, archive_info: ArchiveInfo, hints: Hints,
                             total_budget_s: float, gpu_low_power: bool) -> str: ...
    async def get_session(self, session_id: str) -> SessionRow: ...
    async def list_sessions(self, status: str | None = None) -> list[SessionRow]: ...
    async def update_stage(self, stage_id: str, **fields: object) -> None: ...
    async def record_attempt(self, stage_id: str, started_at: float, ended_at: float,
                             outcome: str, candidates: int, peak_rate: float | None) -> None: ...
    async def record_result(self, session_id: str, password: str, stage_id: str,
                            bkcrack_keys: str | None = None) -> None: ...
    async def append_event(self, session_id: str, stage_id: str | None,
                            level: str, payload: dict[str, object]) -> None: ...
```

### orchestrator

```python
class Orchestrator:
    def __init__(self, repo: SessionRepo, capability: CapabilityProbe,
                 hashcat: HashcatRunner | None, john: JohnRunner | None,
                 bkcrack: BkcrackRunner | None, stages: tuple[Stage, ...]): ...

    async def run_session(self, session_id: str, on_event: EventSink) -> StageResult: ...
    async def pause(self, session_id: str) -> None: ...
    async def resume(self, session_id: str, on_event: EventSink) -> StageResult: ...
    async def cancel(self, session_id: str) -> None: ...
```

---

## 6. Paths and storage layout

```
%LOCALAPPDATA%\UltimateZipPasswordRecover\
├── uzpr.db                          # SQLite, WAL
├── logs\                            # structlog rotating files
├── sessions\
│   └── <session_id>\
│       ├── uzpr.pot                 # shared potfile (cross-stage dedup)
│       ├── stage3.wordlist          # generated candidates
│       ├── masks.hcmask             # derived masks
│       ├── elements.txt             # PRINCE elements file
│       ├── tried.bloom              # Bloom filter (mmap)
│       ├── archive.hash             # zip2john / rar2john output
│       └── <stage_id>.{out,restore,log}
└── tools\                            # bundled binaries (mirrored at install)
    ├── hashcat\
    ├── john\
    └── bkcrack\
```

Path resolution: `uzpr.util.paths.localappdata_dir() / "UltimateZipPasswordRecover"`.

---

## 7. Logging contract

```python
# src/uzpr/util/logging.py exposes:
def configure(log_dir: Path, level: str = "INFO") -> None: ...
def get_logger(name: str) -> structlog.BoundLogger: ...
```

Every module uses `log = get_logger(__name__)`. Every event also lands in the `events` SQLite table when a `session_id` is in scope.

---

## 8. Style and quality bar

- `from __future__ import annotations` at the top of every module.
- All public APIs typed for `pyright --strict`.
- Use `dataclass(slots=True)` for non-frozen, `dataclass(frozen=True, slots=True)` for value objects.
- `async def` for any I/O; never use `requests`, use `httpx`.
- Never call `subprocess.run` blockingly from the event loop — use `anyio.run_process` / `anyio.open_process`.
- Never read/write the SQLite database from multiple threads; the `SessionRepo` owns the writer.
- All times are UNIX epoch floats (`time.time()`), never `datetime` objects in storage.
- Logging through `get_logger`; never `print` outside of `__main__.py`.
