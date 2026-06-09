# Ultimate ZIP Password Recover — Roadmap

> **Status:** Canonical multi-milestone build plan. Derived from the v1.0 architecture. Each milestone has concrete deliverables, files, testable acceptance criteria, and effort estimates (solo developer, ~30 productive hours/week).

---

## Milestone M0 — Foundation (DONE: scaffold, repo)

**Status:** Complete.

### Deliverables
- Git repository initialized with `main` branch protection conventions.
- Python 3.11+ project skeleton (`pyproject.toml`, `uv`/`pip` lockfile, `ruff`, `pyright`, `pytest`).
- Top-level directory layout: `src/uzpr/`, `packaging/`, `tools/`, `vendor/`, `tests/`, `docs/`.
- `README.md` with one-paragraph vision, install placeholder, license notice.
- Canonical architecture committed to `docs/ARCHITECTURE.md`.
- `.gitignore`, `.editorconfig`, `LICENSE` (MIT, pending QFluentWidgets commercial license per Risk #1).
- CI placeholder (`.github/workflows/ci.yml` running `ruff check` + `pyright` + `pytest`).

### Files created
- `pyproject.toml`, `uv.lock`
- `src/uzpr/__init__.py` (with `__version__ = "0.1.0"`)
- `docs/ARCHITECTURE.md`
- `README.md`, `LICENSE`, `.gitignore`, `.editorconfig`
- `.github/workflows/ci.yml`

### Acceptance criteria (testable)
- [x] `git clone && uv sync && uv run pytest` exits 0 with at least one passing smoke test.
- [x] `ruff check src/` and `pyright src/` both exit 0 on empty scaffold.
- [x] CI runs green on `main` HEAD.
- [x] `python -c "import uzpr; print(uzpr.__version__)"` prints `0.1.0`.

### Estimated effort
**Complete.** (Historical estimate: 1 week / 30 hours.)

---

## Milestone M1 — Engine MVP

**Goal:** Prove the cracking pipeline works end-to-end on real archives, headless. No UI. One archive type, one stage, real password recovery via John the Ripper.

### Deliverables
1. **Archive detection** for ZIP family (header parser, AES vs. ZipCrypto classification, GP flag bits, method 99 / extra field 0x9901 walk).
2. **Hash extraction** wrapper around bundled `zip2john.exe` producing hashcat-compatible hashes; mode classifier (17200/17210/17220/17225/17230/13600).
3. **Tool manager** that locates bundled binaries under `tools/` via `sys._MEIPASS`-aware path resolution, runs `WinVerifyTrust` on first use, caches result.
4. **John runner** (`engines/john.py`) with `--session`, `--pot`, status polling regex, `CTRL_BREAK_EVENT` pause, `--restore` resume.
5. **Stage protocol** (`core/stages/protocol.py`) — `Hints`, `StageContext`, `StagePlan`, `StageStats`, `StageResult`, `StageEvent`, `Stage` Protocol — as specified in architecture.
6. **Stage 5 (dictionary attack)** implemented against `rockyou.txt` via john runner.
7. **CLI smoke harness** (`scripts/smoke.py`) that takes `--archive` and `--wordlist`, runs detection → hash extraction → Stage 5, prints found password or "exhausted".
8. **Test archives:** generated fixtures committed under `tests/fixtures/` (small ZipCrypto + WinZip AES archives with known passwords from rockyou's first 100 entries).

### Files to create / modify
- `src/uzpr/archive/detect.py`
- `src/uzpr/archive/zip_inspect.py`
- `src/uzpr/archive/zip2john.py`
- `src/uzpr/archive/hashcat_mode.py`
- `src/uzpr/engines/__init__.py`
- `src/uzpr/engines/john.py`
- `src/uzpr/engines/process_utils.py`
- `src/uzpr/engines/native.py` (pyzipper verifier, used later by Stage 1)
- `src/uzpr/core/stages/protocol.py`
- `src/uzpr/core/stages/s05_dictionary.py`
- `src/uzpr/core/hints.py`
- `src/uzpr/util/paths.py`
- `src/uzpr/util/logging.py`
- `tools/john/zip2john.exe`, `tools/john/rar2john.exe`, `tools/john/run/john.exe` (vendored)
- `scripts/smoke.py`
- `tests/fixtures/*.zip` + generation script `tests/fixtures/build_fixtures.py`
- `tests/unit/test_archive_detect.py`
- `tests/unit/test_hashcat_mode.py`
- `tests/integration/test_john_runner.py`
- `tests/integration/test_stage5_smoke.py`

### Acceptance criteria (testable)
- [ ] `detect.classify("tests/fixtures/zipcrypto_storeonly.zip")` returns `'zip-classic'` and hashcat mode `17210`.
- [ ] `detect.classify("tests/fixtures/winzip_aes256.zip")` returns `'zip-aes'` and hashcat mode `13600`.
- [ ] `detect.classify("tests/fixtures/pkware_strong.zip")` returns `'pkware-strong'` (refused).
- [ ] `zip2john.extract("tests/fixtures/zipcrypto_deflate.zip")` produces a non-empty hash starting with `$pkzip$`.
- [ ] `scripts/smoke.py --archive tests/fixtures/zipcrypto_password_is_letmein.zip --wordlist tests/fixtures/tiny_dict.txt` prints `FOUND: letmein` within 10 seconds.
- [ ] Smoke run against a WinZip AES archive with password `monkey` (from rockyou top-100) recovers the password in under 30 seconds on a developer laptop.
- [ ] John runner supports pause: `runner.pause()` followed by `runner.resume()` resumes from prior progress (verified by `--status` showing non-zero progress after resume).
- [ ] Test coverage `>= 80%` on `archive/` and `engines/john.py` per `pytest --cov`.
- [ ] All bundled binaries pass `WinVerifyTrust` signature verification; result cached.
- [ ] `pyright src/uzpr/{archive,engines,core/stages}` returns zero errors.

### Estimated effort
**3 weeks (~90 hours).** Breakdown: archive detection (1 wk), john runner + process control (1 wk), Stage 5 + smoke harness + fixtures (1 wk).

### Dependencies
- M0 complete.

---

## Milestone M2 — Cascade

**Goal:** All 13 stages implemented, orchestrated by the Python `Orchestrator` over `anyio`, with session persistence, pause/resume, crash recovery, and cross-stage deduplication. Still headless (CLI-driven).

### Deliverables
1. **All remaining engine runners:**
   - `engines/hashcat.py` — `--status-json` streaming, `--session`/`--restore`, stdin `q` pause, watchdog.
   - `engines/bkcrack.py` — list entries, recover keys, decrypt, optional `-r` password recovery.
2. **RAR archive support:** `archive/rar_inspect.py`, `archive/rar2john.py`, RAR3-hp / RAR5 detection.
3. **All 13 stages** (`core/stages/s01_*.py` … `s13_*.py`) implementing the `Stage` Protocol.
4. **Wordlist generation pipeline:**
   - `wordlist/generator.py` — tiered streaming (A/B/C/D), Bloom-deduped.
   - `wordlist/dates.py` — 40 date-encoding variants per date, locale-aware.
   - `wordlist/mutations.py` — case, leet, suffix/prefix combiners.
   - `wordlist/masks.py` — `.hcmask` derivation from charset/length.
   - `wordlist/prince.py` — elements file for pp64.
   - `wordlist/filters.py` — anti-pattern rejection.
5. **Persistence layer** (`persistence/`):
   - Full SQLModel schema matching architecture SQL.
   - `repo.py` SessionRepo facade.
   - `migrations/0001_init.sql`.
   - `encryption.py` DPAPI-protected `hints_json`.
6. **Orchestrator** (`core/orchestrator.py`):
   - Session lifecycle (create, load, pause, resume, cancel).
   - Cascade scheduler iterating stages 1..13 with skip logic.
   - `BudgetAllocator` (greedy EV solver, recomputed on each stage completion).
   - `HeartbeatSupervisor` (5s heartbeat, >30s stale → `crashed`).
   - `CapabilityProbe` with GPU benchmark cache (re-probe if driver changed or >30 days).
7. **Cross-stage dedup** (`core/dedup.py`): Bloom filter front-end + `tried_candidates` SQLite table + shared potfile lock (`core/potfile.py`).
8. **CLI harness** (`scripts/run_session.py`): full session driver — takes archive + JSON hints file + budget, runs full cascade, prints stage-by-stage events.

### Files to create / modify
- `src/uzpr/engines/hashcat.py`
- `src/uzpr/engines/bkcrack.py`
- `src/uzpr/archive/rar_inspect.py`
- `src/uzpr/archive/rar2john.py`
- `src/uzpr/core/stages/s01_known_password.py` … `s13_bkcrack.py` (12 new stage files, s05 already done in M1; refactor to share base)
- `src/uzpr/core/orchestrator.py`
- `src/uzpr/core/budget.py`
- `src/uzpr/core/capability.py`
- `src/uzpr/core/dedup.py`
- `src/uzpr/core/potfile.py`
- `src/uzpr/wordlist/generator.py`, `dates.py`, `mutations.py`, `masks.py`, `prince.py`, `filters.py`
- `src/uzpr/persistence/models.py`, `repo.py`, `encryption.py`
- `src/uzpr/persistence/migrations/0001_init.sql`
- `src/uzpr/util/hashing.py` (blake3 truncated keys)
- `src/uzpr/util/system.py` (WSL detection, battery state)
- `tools/hashcat/hashcat.exe` + OpenCL/ (vendored)
- `tools/bkcrack/bkcrack.exe` (vendored)
- `packaging/rules/OneRuleToRuleThemAll.rule`, `best64.rule`, `dive.rule`
- `scripts/run_session.py`
- `tests/unit/test_budget_allocator.py`
- `tests/unit/test_dedup_bloom.py`
- `tests/unit/test_wordlist_generator.py`
- `tests/unit/test_masks.py`
- `tests/integration/test_orchestrator_cascade.py`
- `tests/integration/test_pause_resume.py`
- `tests/integration/test_crash_recovery.py`
- `tests/integration/test_bkcrack_stage13.py`

### Acceptance criteria (testable)
- [ ] All 13 stages implement `Stage` Protocol; `isinstance(stage, Stage)` returns True for each.
- [ ] Orchestrator runs full cascade on a test ZipCrypto archive with password `summer2019!` (Stage 3 hit) — finds password and persists result, total runtime < 60s on dev laptop.
- [ ] Orchestrator runs full cascade on a WinZip AES archive with random 12-char password not in rockyou and exhausts all paid stages within configured 5-minute budget — result row written with `status='exhausted'`.
- [ ] Stage 13 (bkcrack) recovers internal keys from a ZipCrypto archive given a plaintext sample of ≥12 bytes within 2 hours on a 4-core CPU; produces `bkcrack_keys` in `results` row.
- [ ] Session pause: SIGINT to `scripts/run_session.py` cleanly transitions current stage to `paused`, persists `restore_token`; second invocation with `--resume <session_id>` continues from same stage with cumulative `candidates_tested` increasing.
- [ ] Crash recovery: `kill -9` on running session leaves stage `running` with stale heartbeat; next startup marks stage `crashed`, increments `failure_count`, retries up to 3 times then marks `failed`.
- [ ] Cross-stage dedup: a candidate from Stage 4 wordlist that also appears in Stage 5 dictionary is not retested by the engine (verified by `tried_candidates` row count and engine's reported `candidates_tested`).
- [ ] BudgetAllocator: when Stage 4 finishes EXHAUSTED with 30s of unused budget, the next solve gives Stages 5–12 strictly more budget than the initial seed allocation (verified via `events` table).
- [ ] Detection of RAR3-hp archive returns `'rar3-hp'` and hashcat mode `12500`; RAR5 returns `'rar5'` and mode `13000`.
- [ ] DPAPI-encrypted `hints_json` round-trips correctly; raw bytes in DB do not contain hint plaintext (verified by grep against test hints values).
- [ ] CapabilityProbe re-probes when `device_key` cache entry is older than 30 days OR `driver_version` field differs.
- [ ] Test coverage `>= 80%` overall; `>= 90%` on `core/orchestrator.py` and `core/budget.py`.
- [ ] `pyright src/` returns zero errors.

### Estimated effort
**10 weeks (~300 hours).** Breakdown: hashcat runner + bkcrack runner (2 wk), all 13 stages (3 wk), wordlist pipeline (2 wk), persistence + migrations (1 wk), orchestrator + budget allocator + capability probe (1.5 wk), crash recovery + dedup + tests (0.5 wk).

### Dependencies
- M1 complete (john runner, archive detection, stage protocol).

---

## Milestone M3 — UI

**Goal:** End-user-usable PySide6 + PyQt-Fluent-Widgets desktop application driving the M2 orchestrator. All five navigation pages functional. Intake wizard, hint form, live dashboard, results, settings.

### Deliverables
1. **Application bootstrap** (`__main__.py`, `app.py`): QApplication setup, `qasync` event loop, theme bootstrap, DI wiring of Orchestrator → UI.
2. **Async bridge** (`ui/async_bridge.py`): `EventSink` → Qt signal coalescer at 10 Hz, prevents UI flooding.
3. **MainWindow** with `FluentWindow` + `NavigationInterface` (left rail, 6 destinations + bottom Settings/About).
4. **Home page** — dashboard, recent jobs list, "New Job" CTA.
5. **New Job Wizard** (`SetupWizard`, 5 steps):
   - Step 1: archive drop zone + browse, synchronous detection (<200ms).
   - Step 2: detection summary, `pkware-strong` refusal, bkcrack eligibility toggle.
   - Step 3: full 7-section hint form with live candidate count + ETA footer.
   - Step 4: strategy (budget slider, GPU select, low-power, advanced stage toggles).
   - Step 5: review + launch → creates session row, navigates to Active Jobs.
6. **Active Jobs page** — sidebar of running sessions; main pane with overall progress, 13 StageCards, QtCharts speed sparkline (OpenGL, batched 10 Hz), candidate ticker, pause/resume/cancel.
7. **History page** — sortable table, filter, row-click detail panel with event timeline, "Re-open as new session" action.
8. **Tools page** — GPU info card, benchmark action, "Locate hashcat.exe" override, lazy-download manager for john/rockyou.
9. **Settings page** — `SettingCardGroup` for appearance, performance, storage, privacy, license, updates.
10. **About page** — version, license inventory, signed-by, support links.
11. **Custom widgets:**
    - `widgets/drop_zone.py` — dashed accent border on dragEnter.
    - `widgets/hint_form.py` — 7-section form with tag inputs, live count.
    - `widgets/stage_card.py` — per-stage status, cps EMA, ETA, sample, peak temp.
    - `widgets/speed_chart.py` — `QLineSeries` with OpenGL, 60s window.
    - `widgets/candidate_ticker.py` — last-5 candidates reassurance widget.
12. **Result flow** — on FOUND: `MessageBox` modal with password, copy-to-clipboard, "Decrypt archive now" button (bkcrack or password path).

### Files to create / modify
- `src/uzpr/__main__.py`
- `src/uzpr/app.py`
- `src/uzpr/ui/__init__.py`
- `src/uzpr/ui/main_window.py`
- `src/uzpr/ui/theme.py`
- `src/uzpr/ui/async_bridge.py`
- `src/uzpr/ui/pages/home.py`, `new_job_wizard.py`, `active_jobs.py`, `history.py`, `tools.py`, `settings.py`, `about.py`
- `src/uzpr/ui/widgets/drop_zone.py`, `hint_form.py`, `stage_card.py`, `speed_chart.py`, `candidate_ticker.py`
- `src/uzpr/ui/assets/fonts/Inter-*.ttf`, `JetBrainsMono-*.ttf` (OFL-subset)
- `src/uzpr/ui/assets/icons/` (Fluent UI System Icons)
- `tests/ui/test_wizard_flow.py` (pytest-qt)
- `tests/ui/test_hint_form_live_count.py`
- `tests/ui/test_active_jobs_dashboard.py`
- `tests/ui/test_async_bridge_coalescing.py`

### Acceptance criteria (testable)
- [ ] `python -m uzpr` launches the application, MainWindow displays, theme follows OS (verified via `Theme.AUTO`).
- [ ] Drag-drop a `.zip` onto the drop zone advances the wizard to Step 2 with format detected; rejection of non-ZIP/RAR file shows `InfoBar.error`.
- [ ] Hint form live counter updates within 100ms of any field change; pytest-qt test verifies count reflects added stems/dates.
- [ ] Wizard "Start Recovery" creates a session row in DB and navigates to Active Jobs; pytest-qt asserts both.
- [ ] Active Jobs dashboard displays 13 StageCards; cps EMA updates from real `StageEvent('rate')` events at 10 Hz (verified by mocked orchestrator emitting 100 events/sec; UI receives ≤10 repaints/sec).
- [ ] Speed sparkline renders with `useOpenGL=True`; no missed-frame warnings under sustained 10 Hz update.
- [ ] Pause button on Active Jobs sends pause to orchestrator; StageCard status badge transitions to `paused` within 1s.
- [ ] FOUND result triggers `MessageBox` with password visible and copy-to-clipboard functional.
- [ ] History page lists all past sessions with correct `outcome` and `found_by_stage_id`; row-click opens detail panel with full event timeline.
- [ ] Settings → Theme switch (Light/Dark/Auto) applies immediately without restart.
- [ ] Tools → Re-probe GPU button triggers `CapabilityProbe`; UI updates with detected devices within 30s.
- [ ] `pkware-strong` archive in wizard Step 2 shows `InfoBar.warning` and disables Next button.
- [ ] Manual end-to-end test on real archive: drag `summer2019.zip` (ZipCrypto, password `summer2019!`), fill hints with stem `summer` + date `01/01/2019`, set budget 5min, click Start → password appears in result modal within budget.
- [ ] Test coverage `>= 70%` on `ui/` (lower bar than core; UI is harder to fully unit-test).
- [ ] No GPLv3-incompatible runtime warnings (assumes Risk #1 resolved: QFluentWidgets commercial license purchased).

### Estimated effort
**8 weeks (~240 hours).** Breakdown: bootstrap + async bridge + theme (1 wk), MainWindow + navigation (0.5 wk), Wizard 5 steps (2 wk), Active Jobs dashboard + widgets + QtCharts (2 wk), Home/History/Tools/Settings/About (1.5 wk), result flow + polish + tests (1 wk).

### Dependencies
- M2 complete (orchestrator emits real `StageEvent` stream).
- QFluentWidgets commercial license procured (Risk #1).

---

## Milestone M4 — Polish

**Goal:** Production-quality fit and finish. Theme tokens consistent, animations smooth, accessibility validated, user documentation written, marketing assets produced.

### Deliverables
1. **Theme refinement:** finalize dark surface tokens (`#0F0F12 / #17171C / #1F1F26 / #2B2B33`), text tokens (`#E8E8EE / #B4B4BC / #7A7A84`), accent (`#3B82F6`); light theme palette mirror; verify contrast ratios meet WCAG AA.
2. **Animations:** wizard step transitions, navigation page slide-in, drop-zone dashed-border pulse, FOUND celebration micro-animation (subtle, dismissible).
3. **Accessibility:**
   - Keyboard navigation through entire wizard and active jobs dashboard.
   - Screen-reader labels on all custom widgets (`setAccessibleName`, `setAccessibleDescription`).
   - Focus visible on every interactive element.
   - High-contrast mode honored on Windows.
   - Font scaling at 125%/150%/200% (Windows DPI) without layout breakage.
4. **Error UX:** every failure path has user-friendly message + recovery action (retry, change tool path, open log folder).
5. **Logging polish:** structlog config emits both human (console) and JSON (file) with daily rotation; "Open log folder" action in Settings.
6. **User documentation** (`docs/user/`):
   - `getting-started.md` — install, first job walkthrough.
   - `hints-guide.md` — how to fill each hint section effectively, real examples.
   - `troubleshooting.md` — SmartScreen, AV false positives, missing hashcat, WSL warning.
   - `glossary.md` — what is rockyou, what is a mask, what is bkcrack.
7. **Developer documentation** (`docs/dev/`):
   - `architecture.md` (link to canonical doc).
   - `adding-a-stage.md` — Stage Protocol tutorial.
   - `contributing.md` — code style, test requirements.
8. **Marketing assets** (`marketing/`):
   - Logo (SVG + PNG at 16/32/64/128/256/512 px).
   - 6 product screenshots (Home, Wizard step 3, Active Jobs FOUND state, History, Tools, Settings).
   - 30s screen recording (Wizard → FOUND).
   - Landing page draft copy (`marketing/landing-copy.md`).
   - Open Graph image (1200×630).
9. **Licensing inventory:** `THIRD_PARTY.md` listing every bundled tool, font, icon set, library with license text and verification status.

### Files to create / modify
- `src/uzpr/ui/theme.py` (final tokens)
- `src/uzpr/ui/animations.py` (new — reusable QPropertyAnimation helpers)
- `src/uzpr/util/logging.py` (rotation + JSON formatter)
- `docs/user/getting-started.md`, `hints-guide.md`, `troubleshooting.md`, `glossary.md`
- `docs/dev/architecture.md`, `adding-a-stage.md`, `contributing.md`
- `marketing/logo.svg`, `marketing/icons/*.png`, `marketing/screenshots/*.png`, `marketing/demo.mp4`, `marketing/landing-copy.md`, `marketing/og-image.png`
- `THIRD_PARTY.md`
- `tests/ui/test_keyboard_navigation.py`
- `tests/ui/test_high_dpi_scaling.py`
- `tests/ui/test_contrast_ratios.py`

### Acceptance criteria (testable)
- [ ] Every text/background pair in light AND dark theme meets WCAG AA (≥4.5:1 normal text, ≥3:1 large text) — verified by automated contrast test against `theme.py` token table.
- [ ] Full wizard can be completed without touching the mouse (Tab/Shift+Tab/Enter/Space) — verified by pytest-qt keyboard-only test.
- [ ] At Windows DPI 200%, no widget overflows its container in Active Jobs dashboard at 1920×1080 — screenshot diff test.
- [ ] NVDA screen reader announces wizard step labels, drop zone state, and FOUND result — manual checklist signed off.
- [ ] All 13 StageCards transition status badges with animation under 200ms.
- [ ] Log files rotate at 10 MB, retained for 14 days; `Settings → Open log folder` opens correct path.
- [ ] `docs/user/getting-started.md` walkthrough reproduces step-by-step on a fresh Windows 11 VM by a non-author tester.
- [ ] `THIRD_PARTY.md` accounts for every binary/asset shipped in the installer (verified by diff against `dist/uzpr/` tree).
- [ ] 6 screenshots match the actual app pixel-for-pixel as of release commit (hash-pinned in `marketing/screenshots/MANIFEST.json`).
- [ ] No raw exception traceback ever reaches the user; every error path shows a curated `MessageBox` or `InfoBar` — verified by fault-injection test pass.

### Estimated effort
**4 weeks (~120 hours).** Breakdown: theme + animations (1 wk), accessibility + keyboard nav + DPI (1 wk), docs (1 wk), marketing assets (1 wk).

### Dependencies
- M3 complete.

---

## Milestone M5 — Packaging & release

**Goal:** First publicly downloadable, signed, auto-updating release. CI builds installer on tag push; users install via signed `.exe`; SmartScreen reputation accrual begins.

### Deliverables
1. **PyInstaller spec** (`packaging/win/uzpr.spec`):
   - `onedir` mode, excludes (`tkinter`, `matplotlib`, `QtWebEngine`, `QtMultimedia`, `QtPositioning`, `QtTest`, `QtDesigner`).
   - `--add-binary tools/`, `--add-data packaging/migrations/`, `--add-data packaging/rules/`, `--add-data src/uzpr/ui/assets/`.
   - Runtime path resolution via `sys._MEIPASS` proven in code.
2. **Inno Setup script** (`packaging/win/uzpr.iss`):
   - Dual-mode per-user/per-machine (`PrivilegesRequired=lowest`, `PrivilegesRequiredOverridesAllowed=dialog`).
   - Component selection (offline variant only): hashcat, full john, wordlists.
   - `SignTool=azuresign $f`, `SignedUninstaller=yes`, `CloseApplications=yes`.
   - Silent install flags (`/VERYSILENT /SUPPRESSMSGBOXES /NORESTART`) verified.
3. **Two installer variants:**
   - `uzpr-setup-<ver>.exe` (~80 MB, lazy-downloads hashcat + john).
   - `uzpr-setup-<ver>-offline.exe` (~400 MB, full bundle).
4. **GitHub Actions CI** (`.github/workflows/release.yml`):
   - Triggered on tag push `v*.*.*`.
   - Runs on `windows-latest`.
   - Steps: checkout → setup Python → `uv sync` → `pytest` → PyInstaller build → Inno Setup compile (both variants) → Azure Trusted Signing sign each `.exe` → SHA-256 manifest generation → Ed25519 sign manifest → GitHub Release create with all artifacts.
5. **Azure Trusted Signing integration:** account provisioned, OV identity vetting complete, GitHub Secrets configured (`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`).
6. **Auto-update mechanism** (`src/uzpr/update/`):
   - `checker.py` — GitHub Releases API poll, manifest fetch, Ed25519 verify.
   - `installer_launch.py` — spawn installer with `/VERYSILENT /CLOSEAPPLICATIONS`.
   - Embedded public key (kid=1) for manifest signing.
7. **Release manifest format:** `update-manifest.json` containing `version`, `release_date`, `installers: [{variant, url, sha256, size}]`, `min_supported_from_version`, `kid`, `signed_at`; sidecar `update-manifest.json.sig`.
8. **Microsoft submission:** first signed installer submitted to https://www.microsoft.com/wdsi/filesubmission on release day.
9. **Release checklist** (`docs/release/checklist.md`): version bump, changelog, tag, monitor CI, verify download, install on clean VM, submit to MS.

### Files to create / modify
- `packaging/win/uzpr.spec`
- `packaging/win/uzpr.iss`
- `packaging/win/uzpr.ico`
- `packaging/win/installer-banner.bmp`, `installer-icon.bmp`
- `src/uzpr/update/checker.py`
- `src/uzpr/update/installer_launch.py`
- `src/uzpr/update/__init__.py` (with embedded `UPDATE_PUBLIC_KEYS = {1: b"..."}`)
- `.github/workflows/release.yml`
- `scripts/build_release.py` (local reproduction of CI build)
- `scripts/sign_manifest.py` (Ed25519 signing for release engineer)
- `docs/release/checklist.md`
- `CHANGELOG.md`
- `tests/integration/test_update_checker.py`
- `tests/integration/test_manifest_signature_verify.py`

### Acceptance criteria (testable)
- [ ] Pushing tag `v1.0.0` to GitHub triggers CI; within 30 minutes, GitHub Release contains four artifacts: standard `.exe`, offline `.exe`, `update-manifest.json`, `update-manifest.json.sig`.
- [ ] Both installers are Authenticode-signed by Azure Trusted Signing (verified by `signtool verify /pa /v` returning success).
- [ ] Installing `uzpr-setup-1.0.0.exe` on a fresh Windows 11 VM completes without admin rights when "Install for me only" selected; app launches from Start Menu.
- [ ] Installing same `.exe` with "Install for all users" elevates UAC once and installs under `C:\Program Files\UZPR\`.
- [ ] Silent install `uzpr-setup-1.0.0.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART` completes with exit code 0 and app is launchable.
- [ ] First launch on fresh VM: app starts in <3 seconds; no missing-DLL errors; no `%TEMP%` extraction (verified by `Procmon`).
- [ ] Offline installer launches and runs Stage 5 dictionary attack without any network access (verified by disconnecting NIC before launch).
- [ ] Standard installer lazy-downloads hashcat to `%LOCALAPPDATA%\UltimateZipPasswordRecover\tools\hashcat\` on first GPU stage; integrity verified by SHA-256.
- [ ] Auto-update: setting app version to `0.9.9`, running app, mocking GitHub Releases API to return `v1.0.0` → app shows update `MessageBox`; accepting downloads installer, verifies SHA-256, verifies Ed25519 manifest signature, spawns installer.
- [ ] Tampering with a downloaded installer (flip 1 byte) causes manifest SHA-256 mismatch and installation is refused.
- [ ] Tampering with `update-manifest.json` causes Ed25519 verify failure and update is refused.
- [ ] All bundled `hashcat.exe` / `john.exe` / `bkcrack.exe` retain original publishers' signatures (verified by `Get-AuthenticodeSignature`).
- [ ] CI pipeline reproducible: `scripts/build_release.py` on a developer machine produces installers with identical file structure as CI output (excluding signing).
- [ ] Microsoft file submission acknowledged within 24 hours of release.

### Estimated effort
**3 weeks (~90 hours).** Breakdown: PyInstaller spec + onedir validation (0.5 wk), Inno Setup script + both variants (1 wk), Azure Trusted Signing provisioning + CI pipeline (0.5 wk), auto-update mechanism + manifest signing + tests (0.5 wk), VM testing + Microsoft submission + docs (0.5 wk).

### Dependencies
- M4 complete.
- Azure Trusted Signing OV vetting complete (1–7 days lead time — start during M4).
- Ed25519 key pair generated and private key in AWS KMS (or similar HSM).

---

## Milestone M6 — Monetization

**Goal:** Convert Free users into Pro license holders. Stripe-driven purchase, Ed25519 offline license, in-app activation, Free vs. Pro feature gating live in production.

### Deliverables
1. **License server** (separate repo `uzpr-license-server`, deployed to $5/mo VPS):
   - FastAPI service.
   - Endpoints: `POST /webhook/stripe`, `POST /license/issue` (internal), `POST /license/deactivate` (best-effort).
   - SQLite store of issued licenses (`id`, `email`, `sku`, `issued`, `expires`, `stripe_customer_id`, `machine_fingerprint`, `deactivated`).
   - Ed25519 signing key in AWS KMS (or HashiCorp Vault); never on disk in plaintext.
   - Transactional email via SES/Postmark with license file attached.
2. **Stripe integration:**
   - Products: Pro perpetual ($49), Renewal ($19/yr), Volume 5+ seats ($39 each).
   - Stripe Checkout pages (hosted, no custom UI).
   - Webhook endpoint validates signature, calls `/license/issue`.
3. **In-app licensing** (`src/uzpr/licensing/`):
   - `verify.py` — parse `<payload_b64>.<sig_b64>`, Ed25519 verify against embedded `LICENSE_PUBLIC_KEYS = {kid: bytes}` map.
   - `fingerprint.py` — `HMAC(license.id, CPU_ID)` per Open Question #12 decision.
   - `store.py` — DPAPI-encrypted `license.bin` at `%LOCALAPPDATA%\UltimateZipPasswordRecover\`.
4. **Settings → License page:**
   - "Activate License" — paste field + Activate button.
   - Active state shows email, SKU, expiry, machine binding.
   - "Re-bind to this machine" button (30-day grace per Open Question #12).
   - "Deactivate" button (best-effort POST to server, removes local file).
5. **Feature gating** across the codebase:
   - Pro-only stages (2, 3, 6, 7, 8, 9, 10, 11, 13): `Stage.prepare` returns `outcome=SKIPPED` with `error="pro_required"` if license check fails; UI shows lock badge with upsell tooltip.
   - Pro-only orchestrator features: pause/resume gated, multi-GPU gated, greedy BudgetAllocator falls back to fixed flat split in Free mode.
   - Stage 12 brute force capped at length ≤ 8 in Free mode.
6. **Upsell UX:**
   - Wizard Step 4: locked stages shown disabled with tooltip "Pro feature — unlock for $49".
   - Active Jobs: when cascade skips a Pro stage, `InfoBar` notes the skip with "Upgrade" link.
   - About page: license status prominent.
7. **Purchase flow in-app:**
   - Settings → License → "Buy Pro" opens system browser to Stripe Checkout.
   - Email contains license file + activation instructions.

### Files to create / modify
- **External repo:** `uzpr-license-server/` with FastAPI app, Dockerfile, deploy script.
- `src/uzpr/licensing/__init__.py` (with `LICENSE_PUBLIC_KEYS = {1: b"..."}`)
- `src/uzpr/licensing/verify.py`
- `src/uzpr/licensing/fingerprint.py`
- `src/uzpr/licensing/store.py`
- `src/uzpr/ui/pages/settings.py` (License section additions)
- `src/uzpr/core/orchestrator.py` (gate checks at stage scheduling)
- `src/uzpr/core/stages/protocol.py` (add `requires_pro: bool` to `StagePlan`)
- All Pro-only stage files: add `requires_pro = True` and gated `prepare` logic.
- `src/uzpr/ui/widgets/upsell_badge.py`
- `tests/unit/test_license_verify.py`
- `tests/unit/test_machine_fingerprint.py`
- `tests/integration/test_feature_gating.py`
- `tests/integration/test_activation_flow.py` (pytest-qt)
- `docs/user/purchasing.md`, `docs/user/license-faq.md`

### Acceptance criteria (testable)
- [ ] End-to-end purchase flow (test mode): Stripe Checkout → webhook → license email received within 60 seconds.
- [ ] Valid license activates Pro mode: pasting the license string into Settings, clicking Activate, shows green "Pro Active" within 2 seconds; restart preserves Pro state.
- [ ] Tampered license (single bit flipped in payload or signature) is rejected with `MessageBox` "Invalid license".
- [ ] Expired license (`expires < now`) is rejected with clear expiry message.
- [ ] Machine fingerprint mismatch (e.g., test by editing stored fingerprint) rejects activation with "License is bound to another machine" and offers "Re-bind" action.
- [ ] Re-bind works once per 30 days; second attempt within 30 days shows wait-period message (verified by clock injection in tests).
- [ ] Free mode runs Stages 1, 4, 5, 12 (capped to length ≤ 8); attempts to run Stages 2, 3, 6, 7, 8, 9, 10, 11, 13 result in `SKIPPED` with `error="pro_required"` and UI upsell.
- [ ] Pro mode runs all 13 stages.
- [ ] Pause/Resume button in Active Jobs is disabled in Free mode with tooltip; enabled in Pro mode.
- [ ] Greedy BudgetAllocator active only in Pro; Free mode uses fixed flat split (verified by comparing budget allocation outputs for identical session config under both modes).
- [ ] Stage 12 in Free mode refuses to launch with `?a^9` mask; permits `?a^8`.
- [ ] Deactivate button removes local license file and reverts UI to Free mode within 2 seconds.
- [ ] License server: handles 100 concurrent Stripe webhooks without dropping (load tested with `locust`).
- [ ] License server private key never leaves AWS KMS (verified by audit of code — no `sign()` call accepts a plaintext key).
- [ ] All public keys present in shipped app match the active server-side `kid` values.
- [ ] `docs/user/purchasing.md` walks a tester through purchase + activation on a clean VM successfully.
- [ ] No network call is made during runtime license verification (verified by network capture during normal app operation).

### Estimated effort
**4 weeks (~120 hours).** Breakdown: license server + Stripe integration + AWS KMS (1.5 wk), in-app licensing module + DPAPI store + machine fingerprint (1 wk), feature gating across stages + orchestrator + UI upsell (1 wk), end-to-end testing + docs + VPS deploy (0.5 wk).

### Dependencies
- M5 complete (signed release pipeline must exist so license-bearing builds are trusted).
- Stripe account in good standing.
- VPS provisioned, domain `api.uzpr.app` configured with TLS.
- AWS KMS (or equivalent HSM) configured with Ed25519 key.

---

## Cross-milestone summary

| Milestone | Effort | Cumulative | Calendar (solo, 30h/wk) | Status |
|---|---|---|---|---|
| M0 — Foundation | 30h | 30h | Week 0 | DONE |
| M1 — Engine MVP | 90h | 120h | Weeks 1–3 | Next |
| M2 — Cascade | 300h | 420h | Weeks 4–13 | |
| M3 — UI | 240h | 660h | Weeks 14–21 | |
| M4 — Polish | 120h | 780h | Weeks 22–25 | |
| M5 — Packaging & release | 90h | 870h | Weeks 26–28 | |
| M6 — Monetization | 120h | 990h | Weeks 29–32 | |

**Total v1.0 effort:** ~990 hours / ~33 weeks (~8 months) for a solo developer at 30 productive hours/week. First public signed release at end of M5 (~week 28); first revenue at end of M6 (~week 32).

### Critical-path risks (cross-milestone)
- **Risk #1 (QFluentWidgets GPLv3):** must be resolved before M3 begins, or pivot M3 to a different UI toolkit (PySide6 native widgets — adds ~3 weeks to M3).
- **Azure Trusted Signing OV vetting (1–7 days):** start application during M4 to avoid blocking M5.
- **SmartScreen reputation:** expect 2–6 weeks of warnings after first M5 release; not a blocker but inform marketing copy and `docs/user/troubleshooting.md`.
- **Hit-rate prior calibration:** seeded values may be miscalibrated; monitor first 100 Pro sessions' stage-by-stage outcomes (manually, no telemetry in v1.0) and adjust seeds in v1.1.