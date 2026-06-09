# Ultimate ZIP Password Recover — Tech Stack

> Reference table for the v1.0 build phase. All versions pinned. Install via `pip install -r requirements.txt` unless otherwise noted. Bundled binaries live under `<install>/tools/<name>/` and are resolved by absolute path at runtime.

---

## Runtime & Language

| Name | Version pinned | Role | Install command | Docs URL |
|---|---|---|---|---|
| Python | 3.11.9 | Primary language; `Self` type, perf improvements | `winget install Python.Python.3.11` | https://docs.python.org/3.11/ |
| pip | 24.2 | Package installer | bundled with Python | https://pip.pypa.io/en/stable/ |
| pip-tools | 7.4.1 | Lock dependencies (`requirements.txt` from `.in`) | `pip install pip-tools==7.4.1` | https://pip-tools.readthedocs.io/ |

---

## UI Layer

| Name | Version pinned | Role | Install command | Docs URL |
|---|---|---|---|---|
| PySide6 | 6.7.3 | Qt bindings; FluentWindow base, QProcess, QtCharts, QFileSystemModel | `pip install PySide6==6.7.3` | https://doc.qt.io/qtforpython-6/ |
| PyQt-Fluent-Widgets | 1.7.5 | Fluent 2 widgets (FluentWindow, SetupWizard, ProgressRing, InfoBar, SettingCard). **Commercial license required — see Risk #1** | `pip install "PyQt-Fluent-Widgets[full]==1.7.5" -i https://pypi.org/simple/` | https://qfluentwidgets.com/ |
| qasync | 0.27.1 | Marries Qt event loop to asyncio/anyio | `pip install qasync==0.27.1` | https://github.com/CabbageDevelopment/qasync |
| Inter font | 4.0 | UI typeface (OFL-subset to Latin + Latin-Ext) | download from rsms.me/inter, vendor into `assets/fonts/` | https://rsms.me/inter/ |
| JetBrains Mono | 2.304 | Monospace for passwords/hashes (OFL-subset) | download from jetbrains.com/lp/mono, vendor into `assets/fonts/` | https://www.jetbrains.com/lp/mono/ |
| Fluent UI System Icons | 1.1.265 | Regular + filled icon set (MIT) | download release zip, vendor into `assets/icons/` | https://github.com/microsoft/fluentui-system-icons |

---

## Concurrency & Async

| Name | Version pinned | Role | Install command | Docs URL |
|---|---|---|---|---|
| anyio | 4.6.2.post1 | Structured concurrency (Trio semantics), subprocess streaming | `pip install anyio==4.6.2.post1` | https://anyio.readthedocs.io/ |

---

## Persistence

| Name | Version pinned | Role | Install command | Docs URL |
|---|---|---|---|---|
| SQLite | 3.45.x | Embedded DB in WAL mode (sessions, stages, attempts, results, events, tried_candidates) | bundled with Python | https://www.sqlite.org/docs.html |
| SQLModel | 0.0.22 | Type-safe ORM over SQLite | `pip install SQLModel==0.0.22` | https://sqlmodel.tiangolo.com/ |

---

## Archive & Hash Handling

| Name | Version pinned | Role | Install command | Docs URL |
|---|---|---|---|---|
| pyzipper | 0.3.6 | Native ZIP + WinZip-AES verifier (Stages 1, 2, 3 native streaming) | `pip install pyzipper==0.3.6` | https://github.com/danifus/pyzipper |
| rarfile | 4.2 | RAR reader (shells out to unrar.dll) | `pip install rarfile==4.2` | https://rarfile.readthedocs.io/ |
| unrar.dll | 7.0.4 | RAR archive backend for rarfile (freeware, redistributable) | download from rarlab.com, vendor into `tools/unrar/` | https://www.rarlab.com/rar_add.htm |

---

## Cracking Engines (bundled binaries)

| Name | Version pinned | Role | Install command | Docs URL |
|---|---|---|---|---|
| hashcat | 6.2.6 | GPU engine: stages 4, 7, 8, 9, 12; `--status-json` streaming, `--session`/`--restore` | download `hashcat-6.2.6.7z` from hashcat.net, vendor into `tools/hashcat/` (offline installer) OR lazy-download to `%LOCALAPPDATA%` | https://hashcat.net/wiki/ |
| John the Ripper (jumbo) | bleeding-jumbo 1.9.0-jumbo-1+ (build 2024-09) | CPU engine: stages 5, 6, 10; provides `zip2john`/`rar2john` hash extractors | download from openwall.com/john; bundle `zip2john.exe`+`rar2john.exe` only in standard installer; full distro lazy-downloaded on first CPU stage | https://www.openwall.com/john/doc/ |
| bkcrack | 1.7.0 | Known-plaintext attack on ZipCrypto (Stage 13) | download release from GitHub, vendor into `tools/bkcrack/` (~1 MB, always bundled) | https://github.com/kimci86/bkcrack |

---

## Cryptography & Hashing

| Name | Version pinned | Role | Install command | Docs URL |
|---|---|---|---|---|
| cryptography | 43.0.3 | Ed25519 license + update-manifest signature verification | `pip install cryptography==43.0.3` | https://cryptography.io/ |
| blake3 | 0.4.1 | Fast 16-byte truncated keys for `tried_candidates` dedup | `pip install blake3==0.4.1` | https://github.com/oconnor663/blake3-py |
| pywin32 | 308 | DPAPI for at-rest encryption of `hints_json` and `license.bin` | `pip install pywin32==308` | https://github.com/mhammond/pywin32 |

---

## System & Utilities

| Name | Version pinned | Role | Install command | Docs URL |
|---|---|---|---|---|
| psutil | 6.1.0 | Battery state, process supervision, system probes | `pip install psutil==6.1.0` | https://psutil.readthedocs.io/ |
| structlog | 24.4.0 | Structured JSON logging to file + events table | `pip install structlog==24.4.0` | https://www.structlog.org/ |
| pyopencl | 2024.3 | Secondary GPU detection fallback when hashcat absent | `pip install pyopencl==2024.3` | https://documen.tician.de/pyopencl/ |

---

## Packaging & Installer

| Name | Version pinned | Role | Install command | Docs URL |
|---|---|---|---|---|
| PyInstaller | 6.11.1 | Build `dist/uzpr/` onedir bundle from `packaging/win/uzpr.spec` | `pip install pyinstaller==6.11.1` | https://pyinstaller.org/en/stable/ |
| Inno Setup | 6.3.3 | Build signed installer from `packaging/win/uzpr.iss` | `winget install JRSoftware.InnoSetup` | https://jrsoftware.org/ishelp/ |
| Azure Trusted Signing | service ($9.99/mo) | Code signing for `uzpr.exe` and installers | Azure portal: create Trusted Signing account | https://learn.microsoft.com/en-us/azure/trusted-signing/ |
| azure/trusted-signing-action | v0.5.0 | GitHub Actions step to invoke Trusted Signing in CI | add to `.github/workflows/release.yml` | https://github.com/Azure/trusted-signing-action |

---

## CI/CD

| Name | Version pinned | Role | Install command | Docs URL |
|---|---|---|---|---|
| GitHub Actions | `windows-latest` (Server 2022) | Matrix build on tag push, sign, publish releases | configure `.github/workflows/release.yml` | https://docs.github.com/en/actions |

---

## Bundled Wordlists & Rule Packs

| Name | Version pinned | Role | Install command | Docs URL |
|---|---|---|---|---|
| top10k wordlist | SecLists 2024.3 / `10-million-password-list-top-10000.txt` | Always-bundled common-password list (~150 KB) for Stage 4 | download from SecLists repo, vendor into `wordlists/top10k.txt` | https://github.com/danielmiessler/SecLists |
| rockyou.txt | rockyou (2009 leak, canonical) | Stage 5 dictionary (~140 MB), lazy-downloaded on first dictionary stage | fetched at runtime to `%LOCALAPPDATA%\UltimateZipPasswordRecover\wordlists\` | https://github.com/danielmiessler/SecLists/tree/master/Passwords/Leaked-Databases |
| OneRuleToRuleThemAll | commit `2020-03-04` (canonical) | Hashcat rule pack for Stage 7 | vendor into `packaging/rules/OneRuleToRuleThemAll.rule` | https://github.com/stealthsploit/OneRuleToRuleThemAll |
| best64.rule | hashcat 6.2.6 bundled | Stage 7 baseline rule pack | shipped with hashcat under `rules/best64.rule` | https://hashcat.net/wiki/doku.php?id=rule_based_attack |
| dive.rule | hashcat 6.2.6 bundled | Stage 7 expanded rules | shipped with hashcat under `rules/dive.rule` | https://hashcat.net/wiki/doku.php?id=rule_based_attack |
| KoreLogic rules | KoreLogic-2010 set | Optional advanced rule pack | vendor into `packaging/rules/korelogic.rule` | https://contest-2010.korelogic.com/rules.html |
| hcstat2 (English) | hashcat 6.2.6 bundled | Markov stats file for Stage 11 | shipped with hashcat under `hashcat.hcstat2` | https://hashcat.net/wiki/doku.php?id=markov_attack |
| princeprocessor (pp64) | 0.22 | PRINCE element combiner for Stage 10 | download from hashcat utils, vendor into `tools/hashcat/utils/pp64.exe` | https://github.com/hashcat/princeprocessor |

---

## Licensing Backend (server-side, out of client bundle)

| Name | Version pinned | Role | Install command | Docs URL |
|---|---|---|---|---|
| FastAPI | 0.115.5 | License issuance endpoint on $5/mo VPS | `pip install fastapi==0.115.5` | https://fastapi.tiangolo.com/ |
| Stripe Python SDK | 11.2.0 | Webhook handler for Checkout completion | `pip install stripe==11.2.0` | https://docs.stripe.com/api?lang=python |
| AWS KMS | service | Ed25519 private-key custody | configure via AWS console | https://docs.aws.amazon.com/kms/ |

---

## Files referenced

- `packaging/win/uzpr.spec` — PyInstaller spec (onedir, --add-binary tools)
- `packaging/win/uzpr.iss` — Inno Setup script (dual-mode installer)
- `packaging/migrations/0001_init.sql` — initial SQLite schema
- `packaging/rules/` — bundled rule packs
- `requirements.in` / `requirements.txt` — pip-tools pinned dependency lockfile
- `.github/workflows/release.yml` — CI build + sign + publish