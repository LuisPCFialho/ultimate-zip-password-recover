# Ultimate ZIP Password Recover

**Bulletproof password recovery for ZIP and RAR archives.** A professional desktop application with a cascading multi-stage attack engine that recovers passwords automatically — whether you know the password, remember parts of it, have only hints, or have no memory at all.

> Recover what's yours.

---

## Why this exists

You created a password-protected archive years ago. You forgot the password. Existing tools either:

- Make you choose one attack mode and hope it works
- Lock the good stuff behind expensive enterprise licences
- Have ugly 2002-era interfaces
- Don't fall through to the next attack when one fails

This software runs **thirteen attack stages in cascade**. If a stage fails, the next stage takes over automatically. The user does not need to understand the difference between PRINCE, Markov chains, hybrid masks, or known-plaintext attacks — the engine picks the right stage based on what you tell it.

---

## Features

### Cascading attack engine — 13 stages

The engine starts cheap-and-targeted and walks to expensive-and-broad. Each stage is independently configurable; default settings work for most users.

| # | Stage                              | When it triggers                                    | Engine            |
|---|-------------------------------------|-----------------------------------------------------|-------------------|
| 1 | Known password test                | User typed the full password                        | Native            |
| 2 | Partial mask                       | User knows part of the password                     | hashcat / native  |
| 3 | Hint-driven smart wordlist         | User supplied hints (dates, names, stems)           | Native generator  |
| 4 | Top-10k common passwords           | Always                                              | John / hashcat    |
| 5 | RockYou + SecLists curated         | Always                                              | John / hashcat    |
| 6 | Dictionary + John "Jumbo" rules    | Always                                              | John              |
| 7 | Dictionary + hashcat rule packs    | Always (best64, OneRuleToRuleThemAll, dive)         | hashcat           |
| 8 | Common mask patterns               | Charset/length inferred                             | hashcat           |
| 9 | Hybrid dictionary + mask           | After dict stages                                   | hashcat           |
|10 | PRINCE attack                      | Long passwords likely                               | hashcat / princeprocessor |
|11 | Markov chain attack                | Long passwords with structure                       | hashcat           |
|12 | Pure brute-force                   | Last resort, charset-narrowed                       | hashcat           |
|13 | Known-plaintext attack             | User can supply an unencrypted sample of one file   | bkcrack           |

### Archive support

- **ZIP**: ZipCrypto (PKWARE classic) and AES-128 / AES-256 (WinZip)
- **RAR**: RAR3 (legacy) and RAR5 (modern)

### Engine integration

- **hashcat** — GPU-accelerated, all attack modes, automatic GPU detection (CUDA / OpenCL)
- **John the Ripper jumbo** — CPU, all formats, Jumbo rule system
- **bkcrack** — known-plaintext attack on ZipCrypto (recovers passwords of any length when a single unencrypted file from the archive is available)
- **Native Python fallback** — pyzipper / rarfile for environments without external binaries

All external binaries are auto-downloaded on first run (with checksum verification) or bundled into the installer.

### User experience

- **Modern Fluent design** — Windows 11-style dark/light UI built with PySide6 + PyQt-Fluent-Widgets
- **Guided onboarding** — pick from four "what do you know about the password?" modes
- **Live progress dashboard** — per-stage progress, keys/sec, ETA, live sample of tested candidates
- **Pause and resume** — sessions persist to SQLite; close the app and resume on next launch
- **Auto-extract on success** — password reveal plus one-click full extraction
- **Detailed failure report** — when nothing works, you get a structured report showing every stage attempted, time spent, candidates tested, and recommendations

---

## Status

**Active development.** This README describes the target product. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the design and [`docs/ROADMAP.md`](docs/ROADMAP.md) for current progress.

---

## Legal and ethical use

This software is for recovering passwords on archives **you own** or for which you have **explicit written authorization to access**. Recovering passwords on archives you do not own is illegal in most jurisdictions. The first-run dialog requires confirmation of ownership before any cracking session starts.

The authors and contributors accept no liability for misuse. See [`LICENSE`](LICENSE).

---

## Installation

### Windows

Download the latest installer from [Releases](https://github.com/LuisPCFialho/ultimate-zip-password-recover/releases) and run `UltimateZipRecover-Setup-x64.exe`.

### From source

```powershell
git clone https://github.com/LuisPCFialho/ultimate-zip-password-recover.git
cd "ultimate-zip-password-recover"
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m uzpr
```

Requirements: Python 3.11+ (3.13 recommended), Windows 10/11. Linux and macOS support is planned but not officially supported.

---

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for a full breakdown:

- **Frontend** — PySide6 (Qt 6) with PyQt-Fluent-Widgets for the Windows Fluent look
- **Cracking engine** — Pure Python orchestration layer that spawns and supervises external engines (hashcat, john, bkcrack) and streams their progress back to the UI over an internal asyncio queue
- **Session persistence** — SQLite (via `sqlmodel`) stores in-flight sessions, candidate history, and recovered passwords (encrypted at rest with OS keyring-protected key)
- **Packaging** — PyInstaller one-folder build + NSIS installer; CI builds + signs releases on tag push

---

## Contributing

Issues and pull requests welcome. The codebase aims for:

- **Tested** — every cracking attack module has unit tests with synthetic encrypted archives
- **Type-checked** — `pyright --strict` clean
- **Linted** — `ruff` clean, `black`-formatted
- **Documented** — every public module has a docstring

---

## License

MIT. See [`LICENSE`](LICENSE).
