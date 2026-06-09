# Ultimate ZIP Password Recover — Architecture

> **Status:** Canonical architecture for v1.0 build. All sections below are binding decisions for the build phase. Where research reports disagreed, the chosen option is justified inline. Where they were silent, decisions are marked `(DECISION: ...)`.

---

## Vision and scope

**Vision.** Ultimate ZIP Password Recover (UZPR) is a Windows-first desktop application that recovers forgotten passwords from ZIP and RAR archives using a *transparent, hint-driven cascading attack pipeline*. It targets two audiences: (a) **prosumers** who forgot the password to their own archives and remember fragments ("a name, a date, maybe a suffix"), and (b) **IT/forensics professionals** who need a polished, signed, single-tool wrapper around hashcat / John the Ripper / bkcrack with sane defaults, GPU detection, and session persistence.

**Scope (v1.0):**
- Windows 10/11 x64 only.
- ZIP variants: ZipCrypto (PKZIP modes 17200/17210/17220/17225/17230), WinZip AES (13600), PKWARE strong encryption *detected but not cracked*.
- RAR variants: RAR3 with `-hp` (12500), RAR5 (13000).
- 13-stage cascade orchestrated by a Python `Orchestrator` over `anyio`.
- Hint intake form, smart wordlist generation, mask plan derivation, PRINCE seeding.
- Session persistence (pause/resume/crash recovery).
- GPU auto-detection and CPU/GPU engine routing.
- PySide6 + PyQt-Fluent-Widgets UI, PyInstaller + Inno Setup packaging, Azure Trusted Signing.

**Out of scope (v1.0):**
- macOS, Linux (deferred to v1.1+).
- 7z, encrypted PDF, Office documents.
- Distributed / multi-machine cracking.
- Master-key (hashcat modes 20500/20510) is an "advanced" hidden path, not a first-class UI flow.
- Cloud / SaaS cracking.

**Non-goals:** UZPR is not a generic hashcat launcher. The cascade, hint intake, and budget allocator are the product. Power users who want raw hashcat have hashcat.

---

## High-level architecture

```
+--------------------------------------------------------------------------+
|                                  UI (PySide6 + PyQt-Fluent-Widgets)      |
|   FluentWindow + NavigationInterface                                     |
|     - Home / New Job (Wizard) / Active Jobs / History / Tools / Settings |
|   Live widgets: ProgressBar, ProgressRing, QtCharts (cps sparkline),     |
|                 InfoBar, MessageBox, SettingCard                         |
|   Bridge: qasync — async orchestrator events -> Qt signals (coalesced)   |
+----------------------------|----------------------------------|----------+
                             | StageEvent (progress, sample,    |
                             | rate, log) via EventSink          |
                             v                                  ^
+--------------------------------------------------------------------------+
|                          Orchestrator (Python, anyio)                    |
|   - SessionLifecycle: load/save, pause, resume, cancel                   |
|   - StageScheduler: cascade stages 1..13                                  |
|   - BudgetAllocator: greedy EV solver (re-allocated on each completion)   |
|   - HeartbeatSupervisor: 5s heartbeat, crash detection (>30s stale)      |
|   - DeduplicationLayer: shared potfile + Bloom filter + tried_candidates |
|   - CapabilityProbe: GPU benchmark cache, engine routing                 |
+----------------------------|----------------------------------|----------+
                             |                                  |
        +--------------------+--------------------+             |
        |                    |                    |             |
        v                    v                    v             |
+---------------+   +-----------------+   +---------------+     |
| Native engine |   | hashcat runner  |   | john runner   |     |
| pyzipper      |   | QProcess /      |   | QProcess /    |     |
| rarfile       |   | anyio process   |   | anyio process |     |
| Stage 1,2,3,  |   | Stages 4,7,8,9, |   | Stages 5,6,10 |     |
| 11 (Markov)   |   | 12              |   | (CPU rules)   |     |
+---------------+   +--------+--------+   +-------+-------+     |
                             |                    |             |
                             v                    v             |
                    +-------------------------------+           |
                    | bkcrack runner (Stage 13)     |           |
                    | Known-plaintext attack        |           |
                    +-------------------------------+           |
                             |                                  |
                             v                                  |
+--------------------------------------------------------------------------+
|                      Persistence (SQLite, WAL mode)                      |
|   sessions, stages, attempts, results, events, tried_candidates          |
|   Migrations: packaging/migrations/0001_init.sql, ...                    |
|   Single writer thread, multi-reader; PRAGMA wal_autocheckpoint=1000     |
+--------------------------------------------------------------------------+
                             |
                             v
+--------------------------------------------------------------------------+
|                       OS / Hardware Layer                                |
|  Windows 10/11 x64                                                       |
|  GPU: NVIDIA (CUDA) / AMD (HIP/OpenCL) / Intel (OpenCL)                  |
|  Filesystem: %LOCALAPPDATA%\UltimateZipPasswordRecover\                  |
|  Bundled tools: <install>\tools\{hashcat,john,bkcrack}                   |
|  Keyring: Windows DPAPI (license + hint encryption key)                  |
+--------------------------------------------------------------------------+
```

**Data flow on a session:** UI Wizard → SessionRepo creates row → Orchestrator probes capabilities → BudgetAllocator computes per-stage caps → Stage 1 runs (native verifier) → fail → Stage 2 (mask completion) → ... → Stage k FOUND or all EXHAUSTED → result persisted → UI shows password / failure summary.

---

## Module layout

```
src/uzpr/
├── __init__.py                  # version constant, package metadata
├── __main__.py                  # entry point, sets up qasync + Qt app + Orchestrator
├── app.py                       # QApplication construction, theme/font bootstrap, DI wiring
│
├── core/                        # Engine-agnostic orchestration core
│   ├── __init__.py
│   ├── orchestrator.py          # Orchestrator class: session lifecycle, cascade loop
│   ├── budget.py                # BudgetAllocator: greedy EV solver
│   ├── capability.py            # GPU probe, engine routing heuristic, benchmark cache
│   ├── dedup.py                 # Bloom filter front-end + tried_candidates SQLite layer
│   ├── hints.py                 # Hints dataclass, validation, normalization
│   ├── potfile.py               # Shared potfile lock + read/write helpers
│   └── stages/
│       ├── __init__.py
│       ├── protocol.py          # Stage Protocol, StageContext, StageResult, StageEvent
│       ├── s01_known_password.py    # Stage 1: try user-supplied full password
│       ├── s02_partial_mask.py      # Stage 2: complete partial mask (e.g. "luis????19")
│       ├── s03_smart_wordlist.py    # Stage 3: hint-driven tiered generator
│       ├── s04_top_passwords.py     # Stage 4: top-10k common passwords (hashcat -a 0)
│       ├── s05_dictionary.py        # Stage 5: rockyou + SecLists curated
│       ├── s06_john_rules.py        # Stage 6: john --rules=jumbo on stage3+rockyou
│       ├── s07_hashcat_rules.py     # Stage 7: OneRuleToRuleThemAll + best64 + dive
│       ├── s08_mask_attack.py       # Stage 8: derived masks from charset/length hints
│       ├── s09_hybrid.py            # Stage 9: dict+mask, mask+dict hybrid (-a 6, -a 7)
│       ├── s10_prince.py            # Stage 10: PRINCE with hint-seeded elements file
│       ├── s11_markov.py            # Stage 11: hcstat2 Markov, hint-weighted
│       ├── s12_bruteforce.py        # Stage 12: bounded brute force ?a^N within budget
│       └── s13_bkcrack.py           # Stage 13: known-plaintext attack (oracle)
│
├── engines/                     # External-tool subprocess drivers
│   ├── __init__.py
│   ├── native.py                # pyzipper + rarfile verifier for stages 1, 2, 12 fallback
│   ├── hashcat.py               # HashcatRunner: --status-json streaming, pause/resume
│   ├── john.py                  # JohnRunner: --session, CTRL_BREAK_EVENT, --restore
│   ├── bkcrack.py               # BkcrackRunner: detect, recover keys, decrypt
│   └── process_utils.py         # Windows CREATE_NEW_PROCESS_GROUP, GenerateConsoleCtrlEvent
│
├── archive/                     # Format detection and hash extraction
│   ├── __init__.py
│   ├── detect.py                # ZIP local-header parser, AES vs ZipCrypto classification
│   ├── zip_inspect.py           # Walk entries, find best target for bkcrack/hashcat
│   ├── rar_inspect.py           # RAR3 vs RAR5 detection, header-encrypted check
│   ├── zip2john.py              # Wrapper around bundled zip2john.exe
│   ├── rar2john.py              # Wrapper around bundled rar2john.exe
│   └── hashcat_mode.py          # Map zip2john/rar2john output → hashcat -m mode
│
├── wordlist/                    # Stage 3 generator + mask derivation
│   ├── __init__.py
│   ├── generator.py             # Tiered streaming generator (A/B/C/D), Bloom dedup
│   ├── dates.py                 # Date encodings (40 variants per date, locale-aware)
│   ├── mutations.py             # case_variants, leet_variants, suffix/prefix combiners
│   ├── masks.py                 # derive_masks(): charset/length → .hcmask file
│   ├── prince.py                # build_prince_elements(): elements.txt for pp64
│   └── filters.py               # passes_filters: length, must_have, anti-patterns
│
├── persistence/                 # SQLModel + SQLite layer
│   ├── __init__.py
│   ├── models.py                # SQLModel classes mirroring schema
│   ├── repo.py                  # SessionRepo facade used by Orchestrator
│   ├── encryption.py            # Encrypt hints_json with DPAPI-protected key
│   └── migrations/
│       ├── 0001_init.sql        # Initial schema
│       └── 0002_*.sql           # Future migrations
│
├── ui/                          # PySide6 + PyQt-Fluent-Widgets
│   ├── __init__.py
│   ├── main_window.py           # FluentWindow + NavigationInterface root
│   ├── theme.py                 # setTheme(Theme.AUTO), color tokens, font bootstrap
│   ├── async_bridge.py          # qasync glue, signal coalescer (10 Hz)
│   ├── pages/
│   │   ├── home.py              # Dashboard, recent jobs, quick-start
│   │   ├── new_job_wizard.py    # SetupWizard: archive→detect→hints→strategy→launch
│   │   ├── active_jobs.py       # Running sessions, per-stage progress dashboard
│   │   ├── history.py           # Past sessions (table, filter, re-open)
│   │   ├── tools.py             # GPU info, benchmark, locate hashcat.exe, downloads
│   │   ├── settings.py          # Theme, GPU/CPU mix, low-power, auto-resume, license
│   │   └── about.py             # Version, licenses, signed-by, support links
│   ├── widgets/
│   │   ├── drop_zone.py         # Drag-drop card with dashed accent border
│   │   ├── hint_form.py         # 7-section intake form with tag-inputs + live count
│   │   ├── stage_card.py        # Per-stage status card (state, cps, eta, sample)
│   │   ├── speed_chart.py       # QtCharts QLineSeries with OpenGL, 10 Hz batched
│   │   └── candidate_ticker.py  # Last-5 candidates being tried (reassurance widget)
│   └── assets/
│       ├── fonts/               # Inter + JetBrains Mono (subsetted, OFL)
│       └── icons/               # Fluent UI System Icons (regular + filled, MIT)
│
├── licensing/                   # Offline license validation
│   ├── __init__.py
│   ├── verify.py                # Ed25519 verify, machine fingerprint binding
│   ├── fingerprint.py           # HMAC(MAC + CPU + motherboard_serial)
│   └── store.py                 # DPAPI-encrypted license file at rest
│
├── update/                      # Auto-update mechanism
│   ├── __init__.py
│   ├── checker.py               # GitHub Releases poll, signed manifest verify
│   └── installer_launch.py      # Spawn Inno Setup with /VERYSILENT /CLOSEAPPLICATIONS
│
└── util/
    ├── __init__.py
    ├── paths.py                 # %LOCALAPPDATA% resolution, sys._MEIPASS, work dirs
    ├── logging.py               # structlog config, file rotation
    ├── hashing.py               # blake3 truncated keys for dedup
    └── system.py                # WSL detection, battery state, Win11 24H2 quirks

packaging/
├── win/
│   ├── uzpr.spec                # PyInstaller spec (onedir, --add-binary tools)
│   ├── uzpr.iss                 # Inno Setup script (dual-mode per-user/per-machine)
│   └── uzpr.ico                 # Application icon
├── migrations/                  # SQL files copied into PyInstaller bundle
└── rules/                       # Bundled rule packs (OneRuleToRuleThemAll, KoreLogic)

tools/                           # Bundled external binaries (see Packaging section)
├── hashcat/
├── john/
└── bkcrack/

vendor/                          # Source-of-truth for tools/ (downloaded at build time)
```

---

## Tech stack

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | Solo Python-fluent developer; entire research stack assumed Python. 3.11 for performance + `Self` type. |
| UI framework | PySide6 6.7+ | Official LGPL Qt bindings, native feel, QProcess + QtCharts + QFileSystemModel out of box. |
| UI components | PyQt-Fluent-Widgets 1.7+ | Full Fluent 2 vocabulary (FluentWindow, SetupWizard, ProgressRing, InfoBar). **License: see Risk #1 — commercial license to be purchased before public release to preserve MIT distribution.** |
| Async runtime | anyio (Trio semantics) | Structured concurrency for clean cancellation; trivial subprocess streaming; native to Stage protocol. |
| UI ↔ async bridge | qasync | Standard library for marrying Qt event loop to asyncio/anyio. |
| Persistence | SQLite (WAL) via SQLModel | Single-file, concurrent reads, 10 Hz writes feasible; SQLModel = type-safe + Alembic-friendly. |
| Migrations | Alembic-style linear .sql files | Plain SQL, easy to review and ship in installer. |
| GPU engine | hashcat 6.2+ | Industry standard, --status-json streaming, --session/--restore, MIT license. |
| CPU engine | John the Ripper jumbo (bleeding-jumbo) | zip2john/rar2john are the canonical hash extractors; --session/--restore; GPL-2.0 (lazy-downloaded, not bundled). |
| Known-plaintext | bkcrack | Only viable tool for long/random ZipCrypto passwords; MIT, ~1 MB, bundled. |
| Native ZIP | pyzipper | Drop-in for cpython zipfile + WinZip AES; for Stage 1/2 quick verification. |
| Native RAR | rarfile + unrar.dll | rarfile shells out to unrar; bundle unrar.dll (freeware license, redistribution allowed). |
| Hashing | blake3 | Fast 16-byte truncated keys for tried_candidates dedup. |
| Crypto | cryptography (Ed25519) | License signature verification, update manifest verification. |
| Logging | structlog | Structured JSON logs to file + console; integrates with events table. |
| Packaging | PyInstaller 6.x (onedir) | Mature PySide6 hooks; onedir avoids %TEMP% AV false-positives. |
| Installer | Inno Setup 6.x | Free, Unicode, Pascal scripting, dual-mode per-user/per-machine. |
| Code signing | Azure Trusted Signing ($9.99/mo) | Cloud HSM (no token), CI-friendly, fastest SmartScreen reputation accrual for indie. |
| Auto-update | Custom: GitHub Releases API + Ed25519-signed manifest | ~200 LOC; PyUpdater abandoned, Squirrel.Windows .NET-focused. |
| CI/CD | GitHub Actions (windows-latest) | Free for public repos; matrix build on tag, signed via official Azure action. |
| Licensing | Self-hosted: Stripe → FastAPI → Ed25519 offline license | Avoids Keygen.sh 5-10% take; offline-first; ~400 LOC on $5/mo VPS. |
| Telemetry | None in v1.0 | Privacy-sensitive tool; no phone-home. Update poll only. |

---

## Cascading attack pipeline

The cascade has 13 stages. Stages 1, 2, 3, 13 are **oracle / free-tier** — they run unconditionally when prerequisites are met and consume no EV-pool budget. Stages 4–12 are **paid-tier** — they share the user-set total budget via the greedy EV allocator.

Hit-rate priors below are seed values for the allocator, derived from published cracking surveys (RockYou ≈ 18% on human passwords; common 8-char masks ≈ 35% coverage; KoreLogic rules ≈ +12% over base dictionary). They rank stages correctly; calibration is deferred to v1.1 telemetry.

| # | Stage | Engine | When it runs | Hit rate prior | Time budget share |
|---|---|---|---|---|---|
| 1 | Known password verify | native (pyzipper / rarfile) | If user supplied a candidate password | 1.0 if supplied, else skip | Unbounded (<1s) |
| 2 | Partial mask completion | native + hashcat for >50k | If user supplied partial mask (e.g. `luis????19`) | 0.5–0.9 scaled by `1 − unknown/total` | Unbounded if ≤ 50k candidates, else paid-tier |
| 3 | Hint-driven smart wordlist | native + john | If any hint field non-empty | 0.4 if ≥3 hints, 0.15 otherwise | Unbounded (cap 10M candidates, ~30s on GPU) |
| 4 | Top common passwords | hashcat -a 0 | Always | 0.18 | 5% of paid pool |
| 5 | Dictionary (rockyou + SecLists curated) | hashcat -a 0 / john | Always | 0.20 | 10% of paid pool |
| 6 | john Jumbo rules on stage 3 + rockyou | john --rules=jumbo | Always | 0.12 | 10% of paid pool |
| 7 | hashcat rule packs (OneRule, best64, dive) | hashcat -a 0 -r | Always | 0.15 | 15% of paid pool |
| 8 | Mask attack (derived from charset/length hints) | hashcat -a 3 | If charset/length hints provided | 0.10 | 15% of paid pool |
| 9 | Hybrid attack (dict+mask, mask+dict) | hashcat -a 6 / -a 7 | Always | 0.08 | 10% of paid pool |
| 10 | PRINCE with hint-seeded elements | pp64 → hashcat | If hints non-empty | 0.06 | 10% of paid pool |
| 11 | Markov / hcstat2 (hint-weighted) | hashcat -a 3 -m + hcstat2 | Always | 0.05 | 10% of paid pool |
| 12 | Bounded brute force `?a^N` | hashcat -a 3 | Always (within budget) | `min(0.5, coverable/total)` | 15% of paid pool |
| 13 | bkcrack known-plaintext attack | bkcrack | If ZipCrypto + plaintext sample provided | 1.0 (if eligible) | Unbounded (~1h CPU) |

**Shares above are seeds** for the allocator's first solve; actual allocation is recomputed on every stage completion so that unused budget from EXHAUSTED stages cascades to remaining ones.

**Cross-stage dedup:** every external stage receives `--potfile-path=<shared.pot>` / `--pot=<shared.pot>`. Native stages 1, 2, 3, 11 front-end through a Bloom filter sized for `budget_s × estimated_cps × 2` at 0.1% FPR, backed by the `tried_candidates` SQLite table for crash recovery.

---

## Stage interface

```python
# src/uzpr/core/stages/protocol.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Awaitable, Callable, Protocol, runtime_checkable


class StageOutcome(str, Enum):
    FOUND = "found"
    EXHAUSTED = "exhausted"   # searched assigned keyspace, no hit
    ABORTED = "aborted"        # user paused / cancelled
    FAILED = "failed"          # crashed, out of retry budget
    SKIPPED = "skipped"        # prerequisites not met


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
    case_styles: tuple[str, ...] = ()                  # 'lower'|'Capital'|'UPPER'|...
    must_have: frozenset[str] = frozenset()            # {'digit','symbol','upper','lower'}
    min_length: int = 6
    max_length: int = 16
    locale: str = "en-GB"
    plaintext_sample: Path | None = None               # for stage 13


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
    gpu_devices: tuple[int, ...]   # hashcat -d device ids
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

## Engine integration

All external tools are invoked by **absolute path** to the bundled binary under `<install>/tools/<tool>/`, never via PATH. All commands run with `shell=False` and the work directory set to a per-session scratch folder.

### hashcat command templates

Common flags: `--quiet --status --status-json --status-timer=2 --session=<sess> --restore-file-path=<work>/<sess>.restore --potfile-path=<work>/uzpr.pot --outfile=<work>/<sess>.out --outfile-format=2 -O -w 2 -d <gpu_ids>`.

- **Mode 13600 (WinZip AES), dictionary (Stage 4/5):**
  ```
  hashcat.exe -m 13600 -a 0 <hashfile> <wordlist>
    --session=<sess> --potfile-path=<work>/uzpr.pot
    --restore-file-path=<work> --outfile=<work>/<sess>.out --outfile-format=2
    --status --status-json --status-timer=2 -O -w 2 -d <ids> --quiet
  ```

- **Mode 17225 (PKZIP multi-file mixed), rules (Stage 7):** as above with `-r packaging/rules/OneRuleToRuleThemAll.rule`. *Override:* for 17220/17225 on Ampere GPUs add `--backend-ignore-cuda` (hashcat issue #2813 OOM).

- **Mode 13000 (RAR5), mask attack (Stage 8):**
  ```
  hashcat.exe -m 13000 -a 3 <hashfile> <mask>
    [common flags]
  ```

- **Mode 12500 (RAR3-hp), hybrid (Stage 9):**
  ```
  hashcat.exe -m 12500 -a 6 <hashfile> <wordlist> <mask>     # dict + mask
  hashcat.exe -m 12500 -a 7 <hashfile> <mask> <wordlist>     # mask + dict
  ```

- **Low-power mode (any stage):** append `-w 1 --hwmon-temp-abort=75`, and on NVIDIA `--gpu-temp-retain=70`.

- **Resume:** `hashcat.exe --session=<sess> --restore --restore-file-path=<work>`.

- **Pause:** write `q\n` to stdin; watchdog SIGTERM after `--status-timer + 5s`, SIGKILL after 10s more.

- **Capability probe:** `hashcat.exe -b -m <mode> -d <id> --runtime=10 -O -w 2 --machine-readable`.

### john command templates

Common pattern: `--session=<sess> --pot=<work>/uzpr.pot --format=<zip|zip-aes|rar|rar5>`, cwd=`<install>/tools/john/run`, `creationflags=CREATE_NEW_PROCESS_GROUP` on Windows.

- **Dictionary (Stage 5 CPU fallback):**
  ```
  john.exe --session=<sess> --pot=<work>/uzpr.pot
    --format=zip-aes --wordlist=<wordlist> <hashfile>
  ```

- **Jumbo rules (Stage 6):**
  ```
  john.exe --session=<sess> --pot=<work>/uzpr.pot
    --format=zip-aes --rules=jumbo --wordlist=<stage3_wordlist> <hashfile>
  ```

- **Status poll:** `john.exe --status=<sess>` (cwd same as launch), parsed with regex `r'(\d+)g\s+\S+\s+([0-9.]+)%.*\s+(\d+)p/s'`.

- **Pause:** `GenerateConsoleCtrlEvent(CTRL_BREAK_EVENT, pid)` (Windows).

- **Resume:** `john.exe --restore=<sess>`.

- **Hash extraction:**
  ```
  zip2john.exe <archive.zip> > <work>/<archive>.hash
  rar2john.exe <archive.rar> > <work>/<archive>.hash
  ```

### bkcrack template (Stage 13)

Eligible only when `archive_format == 'zip-classic'` (ZipCrypto, not AES) AND `hints.plaintext_sample` is set.

1. **List entries:**
   ```
   bkcrack.exe -L <target.zip>
   ```

2. **Recover internal keys** (12 B min, 8 contiguous; ~1h CPU):
   ```
   bkcrack.exe -C <target.zip> -c <entryname>
               -P <plain.zip>  -p <entryname>
   ```
   If user provided a raw file (not a ZIP) and the entry is stored:
   ```
   bkcrack.exe -C <target.zip> -c <entryname> -p <plain.bin>
   ```
   If entry is deflated, UZPR's bkcrack runner first tries all 9 zlib levels × {Z_DEFAULT_STRATEGY, Z_FIXED} to recompress `plain.bin` and pick the stream whose first 12 bytes match the encrypted ciphertext XOR keystream-probe.

3. **Output (3 hex words):** `Keys: deadbeef cafebabe 12345678`.

4. **Decrypt entire archive without password:**
   ```
   bkcrack.exe -C <target.zip> -k deadbeef cafebabe 12345678 -D <decrypted.zip>
   ```

5. **Optional: recover original password from keys** (run after stage reports FOUND-keys, surfaces in UI):
   ```
   bkcrack.exe -k deadbeef cafebabe 12345678 -r 8..12 ?p
   ```

---

## Archive detection

UZPR never relies on file extension or filename for format detection. Detection reads the local file header bytes only — zero-cost, deterministic, no cracking attempted.

### Decision tree

```
Input: archive path
  |
  v
[Read first 4 bytes — signature]
  |
  +-- 0x04034B50 (PK\x03\x04) --> ZIP family
  |       |
  |       v
  |    [For each local file header, parse:
  |       GP flag bit 0 = encrypted?
  |       GP flag bit 6 = strong encryption?
  |       compression method = 99 (0x63)?]
  |       |
  |       +-- bit 0 == 0 ---------------------> 'plain'         (no encryption — refuse job)
  |       |
  |       +-- bit 6 == 1 ---------------------> 'pkware-strong' (DECISION: detect, refuse cracking,
  |       |                                                       suggest `john --format=zip`. Hashcat
  |       |                                                       does not support; bkcrack does not support.)
  |       |
  |       +-- method == 99 -------------------> [Walk extra field for header ID 0x9901]
  |       |                                       |
  |       |                                       +-- vendor_id == 'AE' AND strength in {1,2,3}
  |       |                                       |        --> 'zip-aes' (hashcat -m 13600)
  |       |                                       |             AES-{128,192,256} by strength byte
  |       |                                       |             AE-1 or AE-2 by vendor_version
  |       |                                       |
  |       |                                       +-- else -> 'unknown-aes' (refuse, log)
  |       |
  |       +-- method != 99, bit 0 == 1 -------> 'zip-classic' (ZipCrypto / PKZIP stream cipher)
  |                                              [Run zip2john to produce hash, then parse
  |                                               leading tag to pick hashcat mode]
  |                                              |
  |                                              +-- $pkzip$, count=1, CT=0 --> 17210
  |                                              +-- $pkzip$, count=1, CT=8 --> 17200
  |                                              +-- $pkzip$, count=3, all CT=8 --> 17220
  |                                              +-- $pkzip$, count=3, mixed CT --> 17225
  |                                              +-- $pkzip$, count=8 ---------> 17230
  |                                              +-- $zip3$  ------------------> 'pkware-strong' (refuse)
  |
  +-- "Rar!\x1a\x07\x00"  --> RAR3 archive
  |       |
  |       v
  |    [Check header_encrypted flag (-hp)
  |     by reading main header block bytes]
  |       |
  |       +-- header_encrypted == 1 ----------> 'rar3-hp' (hashcat -m 12500)
  |       |                                     [rar2john emits $RAR3$*0*...]
  |       |
  |       +-- encrypted files only (no -hp) --> 'rar3-files' (hashcat -m 12500 still applies
  |                                              for -p; DECISION: in v1.0 we surface both as
  |                                              rar3-hp because rar2john handles both and -p
  |                                              archives are vanishingly rare in the wild.)
  |
  +-- "Rar!\x1a\x07\x01\x00" --> RAR5 archive ---> 'rar5' (hashcat -m 13000)
  |                                              [rar2john emits $rar5$...]
  |
  +-- else --> 'unsupported' (refuse, show "not a ZIP or RAR archive")
```

**Multi-entry ZIP target selection:** for stages 7/13 we prefer the **smallest deflated entry** (fastest hashcat candidate verification; smallest ciphertext for bkcrack keystream recovery). UZPR's `zip_inspect` picks this automatically and surfaces it as "We'll attack `<smallest_entry>` — it's the fastest target" in the wizard.

---

## Hint intake and wordlist generation

### Form fields

The New Job Wizard's "Hints" step is a single scrollable form with seven sections. Every field is optional. Empty form skips Stage 3 entirely and runs the cascade hint-free.

1. **Dates** — repeatable date-picker rows (label + d/m/y picker). Labels include presets: "My DOB", "Partner DOB", "Child DOB", "Anniversary", "Other meaningful date". Free-text label allowed.
2. **Names** — five tag-input (chip list) rows: First names · Surnames · Nicknames/handles · Pet names · Children's names. Comma or Enter to add a chip.
3. **Places** — four tag-inputs: City of birth · Current city · Street name · Country.
4. **Stems / words you reuse** — single tag-input. Free-text personal words you tend to incorporate (e.g. `satabola`, `myg9ewh`).
5. **Suffix / prefix habits** — multi-select chips: years (auto-populated from dates above), `!`, `!!`, `!!!`, `.`, `..`, `?`, `#`, `*`, `123`, `1234`, `12345`, `00`, `01`, `69`, `420`, `007`, plus a custom-add field.
6. **Charset / format hints** — four checkboxes: "Definitely has uppercase / lowercase / digit / symbol". Symbol whitelist: toggle each of `! @ # $ % & * . _ - + ?`.
7. **Length range** — dual slider 4–32, default 6–16. Case-style radio: `lowercase` / `Capitalized` / `UPPER` / `camelCase` / `alternating` / `unsure (try all)` — default `unsure`.

A persistent footer shows **live count: "estimated candidates ≈ X, ETA on your GPU ≈ Ys"** updated on every change. Locale (en-GB default, selectable: en-US, de, fr, pt, es, it, zh) controls date encoding order.

### Generation pipeline (Stage 3)

```
form fields
    |
    v
[normalize] NFC unicode-normalize every text input; strip whitespace; dedupe within-field
    |
    v
[Hints dataclass] frozen, hashable, persisted (DPAPI-encrypted) in sessions.hints_json
    |
    v
[estimate_count] cheap upper bound shown live in UI
    |
    v
[tiered streaming generator] — async iterator, deduped via Bloom filter
    |
    +-- Tier A (~0.1% of 10M budget): raw stems + raw date fragments, no mutation
    +-- Tier B (~5%):  stems × case_variants × top-10 suffixes
    +-- Tier C (~20%): stems × case × dates × suffixes × prefixes
    |                    AND date × suffix only (catches "0501961423" reference case)
    +-- Tier D (~75%): leet variants + double-stem concatenation + symbol injection
    |
    v
[passes_filters] drop if outside length range, missing required charset class,
                 control chars, empty/whitespace, already in Bloom
    |
    v
[output: stage3.wordlist file]
    |
    +--> Stage 3 native engine streams candidates through pyzipper/rarfile
    +--> Stage 6: john --rules=jumbo --wordlist=stage3.wordlist
    +--> Stage 7: hashcat -a 0 -r OneRuleToRuleThemAll.rule stage3.wordlist
    +--> Stage 10: build_prince_elements(stage3 + rockyou[:1000]) → elements.txt → pp64
    +--> Stage 11: hcstat2 trained 10:1 weighted on stage3:rockyou

[derive_masks] from charset/length form fields → .hcmask file (cap 200 masks)
    |
    +--> Stage 8: hashcat -a 3
    +--> Stage 9: hashcat -a 6 / -a 7 (hybrid with stage3.wordlist)
```

**Anti-patterns hard-coded to never emit:** out-of-range length, missing-required-class, ≥3× stem repetition, leet on all-digit stems, suffix == stem (unless explicit double-stem flag), case variant on all-digit stems, mask length 1–3, control chars, unicode normalization duplicates, candidates already in cross-stage Bloom.

Hard global cap: **10M candidates** (configurable 1M–100M in Settings). At 10M, Stage 3 runs in ~30s on a modern GPU for mode 13600, ~3s on hashcat for mode 17225.

---

## Session persistence

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA wal_autocheckpoint = 1000;

CREATE TABLE sessions (
    id              TEXT PRIMARY KEY,        -- uuid4
    archive_path    TEXT NOT NULL,
    archive_sha256  TEXT NOT NULL,
    archive_format  TEXT NOT NULL,           -- 'zip-classic'|'zip-aes'|'rar3'|'rar5'
    hashcat_mode    INTEGER,                 -- 17200/17210/17220/17225/17230/13600/12500/13000
    total_budget_s  REAL NOT NULL,
    hints_json      BLOB NOT NULL,           -- DPAPI-encrypted serialized Hints
    status          TEXT NOT NULL,           -- pending|running|paused|found|exhausted|failed
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
    engine              TEXT NOT NULL,       -- native|hashcat|john|bkcrack
    status              TEXT NOT NULL,       -- pending|queued|running|found|exhausted|skipped|failed|paused|crashed
    budget_s            REAL NOT NULL,
    prior_p             REAL NOT NULL,
    candidates_tested   INTEGER NOT NULL DEFAULT 0,
    elapsed_s           REAL NOT NULL DEFAULT 0,
    restore_token       TEXT,                 -- opaque: workdir for hashcat, session for john, JSON for native
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
    outcome             TEXT,                 -- found|exhausted|aborted|failed|skipped
    candidates_tested   INTEGER NOT NULL DEFAULT 0,
    peak_rate           REAL
);
CREATE INDEX idx_attempts_session ON attempts(session_id);

CREATE TABLE results (
    session_id          TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    password            TEXT NOT NULL,
    found_by_stage_id   TEXT NOT NULL REFERENCES stages(id),
    found_at            REAL NOT NULL,
    bkcrack_keys        TEXT                  -- nullable: "K1 K2 K3" hex if found via stage 13
);

CREATE TABLE events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    stage_id            TEXT REFERENCES stages(id) ON DELETE CASCADE,
    ts                  REAL NOT NULL,
    level               TEXT NOT NULL,        -- debug|info|warn|error
    payload_json        TEXT NOT NULL
);
CREATE INDEX idx_events_session_ts ON events(session_id, ts);

CREATE TABLE tried_candidates (
    hash_blake3         BLOB PRIMARY KEY,     -- 16-byte truncated blake3 of candidate
    first_seen_stage    INTEGER NOT NULL,     -- stage_no
    ts                  REAL NOT NULL
) WITHOUT ROWID;

CREATE TABLE capability_cache (
    device_key          TEXT PRIMARY KEY,     -- sha1(name|driver|vram)
    device_name         TEXT NOT NULL,
    driver_version      TEXT NOT NULL,
    benchmarks_json     TEXT NOT NULL,        -- {mode: H/s}
    probed_at           REAL NOT NULL
);
```

**Storage location:** `%LOCALAPPDATA%\UltimateZipPasswordRecover\uzpr.db`. Work directories (per-session scratch): `%LOCALAPPDATA%\UltimateZipPasswordRecover\sessions\<session_id>\`.

---

## UI navigation

```
[App start]
    |
    v
[MainWindow: FluentWindow + NavigationInterface (left rail)]
    |
    +-- Home (FIF.HOME)               -- dashboard, recent jobs, "New Job" CTA
    +-- New Job (FIF.ADD)             -- SetupWizard, 5 steps
    +-- Active Jobs (FIF.PLAY)        -- running sessions with live dashboard
    +-- History (FIF.HISTORY)         -- past sessions, filter, re-open
    +-- Tools (FIF.DEVELOPER_TOOLS)   -- GPU info, benchmark, download manager
    +-- Settings (FIF.SETTING)        -- bottom rail
    +-- About (FIF.INFO)              -- bottom rail

[Home page transitions]
    "New Job" CTA  -->  New Job (Wizard step 1)
    Recent job row click  -->  Active Jobs (focused on that session) or History detail

[New Job Wizard — SetupWizard]
    Step 1: Select archive
        - Drag-drop CardWidget (dashed accent border on dragEnter)
        - "Browse..." PrimaryPushButton -> QFileDialog (*.zip, *.rar)
        - On drop/select: detect format synchronously (<200ms), preview entries
        Next-> Step 2

    Step 2: Detected format & encryption
        - Read-only summary card: format, encryption, suggested hashcat mode
        - If 'pkware-strong': InfoBar.warning + Next disabled
        - If 'zip-classic': "Do you have a copy of any of these files?" toggle
            (yes -> Step 4 will surface bkcrack path)
        Next-> Step 3

    Step 3: Hints intake form (the 7-section form)
        - Live candidate-count + ETA in footer
        - "Skip hints" button (proceeds with empty Hints, skips Stage 3)
        Next-> Step 4

    Step 4: Strategy
        - Total time budget slider: 5min / 30min / 2h / 8h / 24h / custom
        - GPU selection (auto-detected, override allowed)
        - Low-power mode toggle (forces -w 1, --hwmon-temp-abort=75)
        - "Advanced": expose stage enable/disable toggles
        Next-> Step 5

    Step 5: Review & Launch
        - Summary: archive, format, hints summary, budget, stages enabled
        - PrimaryPushButton "Start Recovery"
        Click-> create session row, navigate to Active Jobs

[Active Jobs page]
    - Sidebar: list of running sessions
    - Main pane (per selected session):
        * Overall ProgressBar (0-100% of stages completed weighted by budget)
        * Per-stage StageCard grid (13 cards): name, status badge, mini progress,
          cps EMA, ETA, last-5 candidates ticker, peak GPU temp
        * Speed sparkline (QtCharts, 60s window, useOpenGL=True, 10 Hz batched)
        * Action buttons: Pause / Resume / Cancel
    - On FOUND: MessageBox modal with password (copy-to-clipboard), optional
      "Decrypt archive now" button (uses bkcrack keys or password)

[History page]
    - Table: archive name, format, outcome, found-by-stage, duration, date
    - Row click -> detail panel showing full event timeline + result
    - "Re-open as new session" action (reuses hints, fresh budget)

[Tools page]
    - GPU detection card (re-probe button)
    - Benchmark card (run hashcat -b across all modes)
    - "Locate hashcat.exe" PushSettingCard (override bundled)
    - Download manager: status of john jumbo full distro, optional wordlists

[Settings page] — SettingCardGroup-based
    - Appearance: SwitchSettingCard (Theme: Auto/Light/Dark)
    - Performance: OptionsSettingCard (Workload: Background/Balanced/Max)
    - Performance: SwitchSettingCard (Low-power on battery)
    - Storage: PushSettingCard (Open session work dir, Clear old sessions)
    - Privacy: SwitchSettingCard (Auto-delete hints after session)
    - License: PushSettingCard (Activate / Paste license key)
    - Updates: SwitchSettingCard (Check on startup)
```

**Modal/dialog conventions:** confirmations use `MessageBox`, destructive actions ("Cancel session — lose progress?") use `MessageBox` with accent button on Cancel (preserve) and danger button on Confirm. Toasts use `InfoBar.success` / `.warning` / `.error` anchored bottom-right with 5s auto-dismiss.

**Theme:** `setTheme(Theme.AUTO)` at startup. Dark surfaces `#0F0F12 / #17171C / #1F1F26 / #2B2B33`, text `#E8E8EE / #B4B4BC / #7A7A84`, accent `#3B82F6`. Fonts: Inter (UI) + JetBrains Mono (passwords/hashes), embedded via `QFontDatabase.addApplicationFont` from `assets/fonts/` (OFL-subset to Latin + Latin-Ext).

---

## GPU detection and engine selection

### Detection (layered fallback)

```
1. Probe hashcat -I --machine-readable      (authoritative source of truth)
   - If hashcat missing OR errors: fall through
   - If returns >=1 GPU device: use it
2. Probe pyopencl.get_platforms()            (cross-platform secondary)
   - If returns >=1 GPU device: use it (but warn 'hashcat not detected, install required')
3. Probe PowerShell Get-CimInstance Win32_VideoController  (cosmetic display info only)
   - Used to populate human-readable model name in UI; never used for decision-making
```

For each detected device, record: `backend (CUDA/OpenCL/HIP/Metal)`, `device_id (1-based for hashcat -d)`, `vendor`, `name`, `vram_total_mb`, `vram_free_mb`, `driver_version`.

### Numeric thresholds

| Check | Threshold | Action |
|---|---|---|
| VRAM total | < 2 GB | **Refuse** to use device for GPU stages |
| VRAM total | 2–4 GB | Warn but allow |
| VRAM total | ≥ 4 GB | Prefer |
| VRAM free at probe | < 512 MB | Refuse |
| Device smoketest | hashcat `-b -m 0 --runtime=2 -d <id>` errors | Reject device, mark in cache |
| Capability cache age | > 30 days OR driver version changed | Re-probe (10s per mode: 13600, 17225, 13000) |
| Workload default | `-w 2` (Balanced) | Default for all stages |
| Workload max exposed | `-w 3` (Max) | Hidden behind "I understand my desktop will be unresponsive" toggle |
| Workload `-w 4` (Nightmare) | **Never** exposed | OS-hang risk |
| Optimized kernel `-O` | Always on for ZIP/RAR modes | Cap password length to ~31–32 (surfaced in UI) |
| Thermal abort | `--hwmon-temp-abort=90` (default) / `=75` (low-power) | Hard-stop on overheat |
| Battery detected | `psutil.sensors_battery().power_plugged == False` | Refuse GPU stages without explicit confirmation; default route to CPU john |
| WSL2 detected | `uname -r` contains 'microsoft' | Warn known-issue (hashcat #4133); recommend native Windows |

### Engine routing per stage

```
HASHCAT_STARTUP_S = 6.0      # measured cold-start median
JOHN_STARTUP_S    = 0.15

CPU_HS_BY_MODE = {
    13600: 80_000,           # WinZip-AES   on modern Ryzen 5/7
    17225: 25_000_000,       # PKZIP        (very fast on CPU too)
    13000: 6_000,            # RAR5         (very slow on CPU)
    12500: 100_000,          # RAR3-hp
}

# For each stage, compute:
cpu_time = JOHN_STARTUP_S + candidates / CPU_HS_BY_MODE[mode]
gpu_time = HASHCAT_STARTUP_S + candidates / capability_cache[mode]
pick = 'hashcat' if (gpu_available and gpu_time < cpu_time) else 'john'

# Stage-specific overrides:
# Stage 1 (known password):   ALWAYS native pyzipper/rarfile (1 candidate, no subprocess)
# Stage 2 (partial mask):     native if candidates <= 50_000, else hashcat
# Stage 3 (hint wordlist):    native streamer feeds hashcat -a 0 stdin (mode 13600/12500/13000),
#                             native pyzipper for mode 17200/17225 (10M candidates ~3s on GPU regardless)
# Stage 6 (john rules):       ALWAYS john (rules engine is john-native)
# Stage 7 (hashcat rules):    ALWAYS hashcat
# Stage 13 (bkcrack):         ALWAYS bkcrack (no choice)
```

### Multi-GPU device selection

Score each detected GPU and pass `-d <id>` explicitly to hashcat (never let hashcat auto-select):

```
score = base[vendor] + vram_bonus + dedicated_bonus
  base = {NVIDIA: 100, AMD: 90, Apple: 80, Intel-Arc: 70, Intel-iGPU: 10}
  vram_bonus       = min(vram_total_gb, 24) * 2
  dedicated_bonus  = 50 if type == 'discrete' else 0
```

Pick top-scoring device by default. Settings page lets user multi-select.

---

## Packaging and distribution

### PyInstaller layout (onedir mode)

```
dist/uzpr/
├── uzpr.exe                      # Signed launcher
├── _internal/                    # PyInstaller runtime + Python stdlib + site-packages
│   ├── PySide6/                  # Qt DLLs
│   ├── base_library.zip
│   ├── python311.dll
│   └── ...
├── tools/                        # Bundled binaries (inline in installer)
│   ├── hashcat/
│   │   ├── hashcat.exe           # ~150 MB optional, opt-out in installer
│   │   └── OpenCL/
│   ├── john/
│   │   ├── zip2john.exe          # ~5 MB minimal subset, always bundled
│   │   ├── rar2john.exe
│   │   └── run/                  # placeholder; full john lazy-downloaded on first CPU run
│   └── bkcrack/
│       └── bkcrack.exe           # ~1 MB, always bundled
├── wordlists/
│   ├── top10k.txt                # ~150 KB, always bundled
│   └── rockyou.txt               # lazy-downloaded to %LOCALAPPDATA% on first dictionary stage
├── packaging/
│   ├── rules/                    # OneRuleToRuleThemAll, best64, dive, KoreLogic, jumbo
│   └── migrations/               # SQL migration files
└── assets/
    ├── fonts/                    # Inter + JetBrains Mono (OFL, subsetted ~400 KB)
    └── icons/                    # Fluent UI System Icons (MIT)
```

PyInstaller spec excludes `tkinter`, `matplotlib`, `QtWebEngine`, `QtMultimedia`, `QtPositioning`, `QtTest`, `QtDesigner` to keep size down. Binaries resolved at runtime via `Path(sys._MEIPASS or PROJECT_ROOT) / 'tools' / ...`.

**Two installer variants:**
- `uzpr-setup-<ver>.exe` — standard, ~80 MB (bkcrack + zip2john/rar2john only; hashcat and john lazy-downloaded on first use).
- `uzpr-setup-<ver>-offline.exe` — offline / air-gapped, ~400 MB (hashcat and full john pre-bundled).

### Installer flow (Inno Setup)

```
1. Welcome page (skinned to match Fluent dark theme via [Setup] WizardImageFile)
2. License page (UZPR license + tools' license inventory)
3. Privilege selection:
     - "Install for me only" (default, no UAC, target %LOCALAPPDATA%\Programs\UZPR)
     - "Install for all users" (UAC elevation, target Program Files)
4. Install location (auto-resolved by mode)
5. Components (offline installer only):
     - Core application [required]
     - hashcat GPU engine (~150 MB) [default checked]
     - John the Ripper full distribution (~300 MB) [default unchecked]
     - Wordlists pack (~150 MB) [default unchecked]
6. Start Menu folder
7. Ready to install
8. Install progress
9. Finish: launch UZPR option (default checked)
```

Inno script flags: `PrivilegesRequired=lowest`, `PrivilegesRequiredOverridesAllowed=dialog`, `DisableDirPage=no`, `SignTool=azuresign $f`, `SignedUninstaller=yes`, `CloseApplications=yes`, `RestartApplicationsAfterUpdate=yes`. Silent install: `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART`.

### Code signing plan

- **Service:** Azure Trusted Signing ($9.99/mo base + $0.005/sig).
- **Identity:** OV-equivalent organization validation (1–7 days vetting).
- **What gets signed:**
  - `uzpr.exe` (launcher)
  - `uzpr-setup-<ver>.exe` (installer)
  - `uzpr-setup-<ver>-offline.exe` (offline installer)
  - **NOT** the bundled `hashcat.exe` / `john.exe` / `bkcrack.exe` — those carry their original publishers' signatures (verified by `WinVerifyTrust` on first run; result cached in `capability_cache`).
- **CI integration:** `azure/trusted-signing-action@v0.5.0` in GitHub Actions, secrets `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, endpoint `https://eus.codesigning.azure.net/`.
- **Cert validity:** plan annual rotation per CA/B Forum 458-day max (effective March 2026).
- **SmartScreen accrual:** expect 2–6 weeks of "Windows protected your PC" warnings on first signed build despite valid cert; documented in README and installer Finish page. Submit clean installer to https://www.microsoft.com/wdsi/filesubmission on first release.

### Auto-update flow

```
1. On app startup (async, non-blocking, can be disabled via Settings):
   GET https://api.github.com/repos/<org>/uzpr/releases/latest
2. Compare tag_name to __version__; if newer:
3. Fetch update-manifest.json (release asset) and update-manifest.json.sig
4. Verify Ed25519 signature with embedded public key (rotated annually, kid field)
5. Show MessageBox: "Version X is available. Update now?"
6. On accept: download installer to %TEMP%, verify SHA-256 from manifest
7. Spawn installer with /VERYSILENT /CLOSEAPPLICATIONS /RESTARTAPPLICATIONS
8. Exit current process (Restart Manager handles file locks)
```

---

## Monetization model

> **DECISION:** UZPR ships as Free + Pro tiers. Rationale: bkcrack and hint-form value are differentiators worth charging for; basic dictionary cracking is table-stakes and should be free to build install base and SmartScreen reputation.

### Tiers

| Feature | Free | Pro |
|---|---|---|
| Archive detection (ZIP/RAR, all variants) | ✓ | ✓ |
| Stage 1: Known password verify | ✓ | ✓ |
| Stage 4: Top 10k passwords | ✓ | ✓ |
| Stage 5: Dictionary (rockyou) | ✓ | ✓ |
| Stage 12: Brute force (length ≤ 8) | ✓ | ✓ |
| GPU acceleration (hashcat) | ✓ | ✓ |
| Stage 2: Partial mask completion | — | ✓ |
| Stage 3: Hint-driven smart wordlist | — | ✓ |
| Stage 6/7: Rule packs (Jumbo, OneRule) | — | ✓ |
| Stage 8/9: Mask + hybrid attacks | — | ✓ |
| Stage 10: PRINCE | — | ✓ |
| Stage 11: Markov | — | ✓ |
| Stage 13: bkcrack known-plaintext | — | ✓ |
| Session pause/resume | — | ✓ |
| Multi-GPU selection | — | ✓ |
| Budget allocator (EV-based cascade) | Fixed flat split | ✓ Greedy |
| Priority email support | — | ✓ |

**Pricing (DECISION):** Pro = **$49 perpetual license + 1 year of updates**, $19/yr for further updates after year 1. Single-machine, transferable. Volume discount for orders ≥5 seats.

### License validation flow

```
[Purchase]
User -> Stripe Checkout -> Stripe Webhook -> https://api.uzpr.app/license/issue
                                                |
                                                v
                                      [FastAPI server, $5/mo VPS]
                                      Generate UUID + payload:
                                        {id, email, sku, issued, expires, kid}
                                      Sign with Ed25519 private key (AWS KMS)
                                      license_file = base64(payload) + "." + base64(sig)
                                      Email license_file to customer

[Activation in UZPR]
Settings -> "Activate License" -> Paste license_file
   |
   v
1. Parse "<payload_b64>.<sig_b64>"
2. Verify Ed25519 signature with embedded public key (matched by kid field)
3. Verify expires > now (or null = perpetual)
4. Compute machine_fingerprint = HMAC(license.id, MAC + CPU_ID + motherboard_serial)
5. Store: license_file + machine_fingerprint -> DPAPI-encrypted at
   %LOCALAPPDATA%\UltimateZipPasswordRecover\license.bin
6. UI: switch to "Pro" mode

[Runtime check — every app start]
1. Read DPAPI-encrypted license.bin
2. Re-verify Ed25519 signature
3. Re-compute machine_fingerprint and compare to stored
   - Mismatch -> "License is bound to another machine; deactivate or contact support"
4. Check expires (warn 30 days before expiry)
5. Enable Pro features if valid; otherwise gate to Free
```

**Offline-first guarantees:** no network call required at runtime after activation. License verification is local. Server is only hit on purchase (Stripe webhook → email) and explicit "Deactivate this machine" action (best-effort POST, license still works locally until removed).

**Key rotation:** payload includes `kid` (key id). UZPR embeds public keys for kid 1..N. When key 1 is rotated, app update bumps to embed key 2 alongside key 1; old licenses remain valid.

---

## Risks and mitigations

| # | Risk | Mitigation |
|---|---|---|
| 1 | **PyQt-Fluent-Widgets GPLv3 vs. project MIT license** — distributing MIT binary linking GPLv3 component is a license violation; blocks public release. | Purchase QFluentWidgets commercial license in week 1 (preserves MIT). Fallback: relicense UZPR to GPLv3. Decision must be made before first signed release. |
| 2 | **SmartScreen "Unrecognized app" warning** even with valid Azure Trusted Signing cert until reputation accrues (~2–6 weeks). | Azure Trusted Signing chosen for fastest accrual; submit installer to Microsoft for malware analysis on first release; document "More info → Run anyway" prominently in README and installer Finish page. |
| 3 | **AV false positives on bundled hashcat/john** — they ARE password crackers, may be flagged "HackTool". | Sign each binary with original publishers' certs (verified at runtime, not re-signed by UZPR). Install to %LOCALAPPDATA% (per-user, less AV-aggressive). Document Defender exclusion paths in user manual. |
| 4 | **hashcat --status-json malformed in some kernel modes** (issue #4393). | Wrap each line in `try/except json.JSONDecodeError`, fall back to scraping human status line, log parse failures to events table, pin tested hashcat version. |
| 5 | **PKZIP 17220/17225 CUDA OOM on Ampere GPUs** (issue #2813) even on 10 GB+ cards. | For modes 17220/17225 on detected Ampere devices, always pass `--backend-ignore-cuda` to force OpenCL backend; on retry-OOM, also reduce with `-n 1 -u 1`. |
| 6 | **Bundled john GPL-2.0 redistribution obligations**. | Lazy-download full john distribution from Openwall on first CPU stage; bundle only zip2john/rar2john as MIT-compatible-subset (after license review confirms acceptable redistribution under OpenSSL exception). Document all licenses in `THIRD_PARTY.md`. |
| 7 | **Privacy of hint data** — DOBs, names, addresses are PII. | DPAPI-encrypt `hints_json` at rest using OS keyring. "Auto-delete hints after session" toggle (default-on in Pro). Never log hint values, only candidate counts. No network transmission ever. |
| 8 | **Long-running session crashes lose progress.** | Heartbeat every 5s into `stages.last_heartbeat_at`; on startup, stale heartbeats (>30s) mark stage `crashed` with failure_count increment; per-stage retry cap of 3; resume from `restore_token`. SQLite WAL with `wal_autocheckpoint=1000` and explicit checkpoint at every stage transition. |
| 9 | **License private key compromise = unlimited free licenses minted.** | Store Ed25519 private key in AWS KMS (not env var). Include `kid` in payload; rotate annually; app embeds public keys for all currently-valid kids. Kill-switch ability in app v2+ to require online re-validation in case of breach. |
| 10 | **Candidate explosion in Stage 3** — chatty user with 20 stems × 10 dates → 10⁹+ candidates, freezing UI. | Hard global cap (10M default, configurable 1M–100M); streaming async iterator never materializes full list; live UI counter during form entry showing projected count + ETA + warning when exceeding budget; Bloom filter sized for budget; tiered generation guarantees highest-EV candidates run first even when under-budgeted. |

---

## Open questions (for later phases)

1. **macOS support timing.** Apple Developer cert ($99/yr) + notarization required. (DECISION: deferred until Windows Pro MRR exceeds $1k/mo.) Need to revisit hashcat Metal backend wiring and PyQt-Fluent-Widgets behavior on macOS.

2. **Linux distribution format.** AppImage vs. Flatpak vs. .deb/.rpm. Lower-priority than macOS for this product category.

3. **Telemetry for prior calibration.** Hit-rate priors are seeded from public surveys, but real calibration requires opt-in success-by-stage histograms. Privacy/UX tradeoff TBD; defer to v1.2.

4. **Master-key (hashcat modes 20500/20510) advanced UI.** Currently hidden; if Stage 13 produces bkcrack keys frequently, expose a one-click "recover original password from keys" flow.

5. **PKWARE strong encryption ($zip3$).** Currently detected and refused. If demand surfaces, integrate `john --format=zip` for CPU-only attack (no hashcat support). Unlikely worth the engineering investment.

6. **Distributed cracking** (single user, multiple machines they own). Out of scope for v1.0; potential v2 feature using NATS or a simple coordinator service.

7. **7-Zip and Office document support.** Different threat model (different hashcat modes, different hash extractors). Possible separate product or v1.5 expansion.

8. **PCFG-based generator** (PCFG-Cracker integration) for Stage 3 Tier-D replacement. Higher quality than current Cartesian-product approach but requires training data and 4-6 weeks of integration; defer to v1.2 if hit-rate telemetry shows Stage 3 underperforming.

9. **Cloud GPU bursting.** Pro+ tier offering to spin up RunPod/Vast.ai instances for stages 11/12. Strong business case but pushes UZPR into SaaS territory and requires a hosted control plane.

10. **In-app store / accelerated activation.** If Microsoft Store policy permits "password recovery" tools (currently ambiguous), publishing there gives free signing + instant SmartScreen trust but takes 30% revenue cut and forces MSIX sandbox limitations. Re-evaluate at $5k/mo MRR.

11. **Locale expansion for hint form.** Currently en-GB/en-US/de/fr/pt/es/it/zh. Cyrillic / CJK transliteration tables for non-Latin passwords. v1.1+.

12. **Hardware fingerprint stability** — motherboard replacements, RAM upgrades, MAC changes shouldn't invalidate licenses. (DECISION: bind to CPU_ID only + 30-day grace re-bind via Settings → "Re-bind this license to this machine".) Validate against real customer churn data after first 6 months.