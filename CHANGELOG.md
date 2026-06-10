# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-06-10

### Added

- **13-stage cascade recovery pipeline**: ZipCrypto known-plaintext (bkcrack) → top
  passwords → dictionary (top10k → top100k → rockyou → HIBP top-1M) → rules
  (best64 → OneRuleToRuleThemAll → pantagrule → dive) → hybrid → PRINCE →
  combinator → Markov → brute force.
- **bkcrack auto-detect** (Stage 13): recovers any ZipCrypto password — including
  12-char random — in seconds when the archive contains a STORED entry with a known
  magic header (PNG, PDF, OLE, ZIP, GIF). Zero user input required.
- **Portuguese locale pack** (pt-PT): wordlists for Liga clubs (Benfica/Porto/
  Sporting), Portuguese names, cities, and common words — tried before rockyou.
- **Stage 14 Combinator** (`hashcat -a 1`): word-pair concatenation; pt-aware.
- **EV scheduler**: stages ordered by `prior / expected_seconds`; highest-yield
  attacks run first within any budget.
- **PRINCE unhinted**: multi-word concatenation even without user hints.
- **Simple Mode wizard**: 3-step flow (archive → optional hints → honest estimate).
  Honest capability estimates based on format and hints provided.
- **Advanced Mode**: per-stage controls, budget input, GPU selector, plaintext-
  sample picker. Toggle persisted to `~/.uzpr/settings.json`.
- **License system**: ed25519 self-signed tokens; `is_pro()` gate; offline
  issuance via `scripts/licensing/issue_license.py`.
- **Ko-fi nag screen**: after successful recovery and every 3rd launch; max once
  per day; skipped for Pro users.
- **Auto-update checker**: polls GitHub Releases API, 24 h throttle, silent on
  network errors.
- **winget manifest**: `winget install LuisPCFialho.UltimateZipPasswordRecover`.
- **Landing page**: `https://luispcfialho.github.io/ultimate-zip-password-recover/`.

### Supported formats

- ZIP — ZipCrypto (PKWARE traditional)
- ZIP — WinZip AES-128 / AES-256
- RAR3 (HP-encrypted)
- RAR5

### System requirements

- Windows 10 / 11 (64-bit)
- ~200 MB disk space
- GPU optional (hashcat accelerates dictionary/mask/rules stages)

[Unreleased]: https://github.com/LuisPCFialho/ultimate-zip-password-recover/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/LuisPCFialho/ultimate-zip-password-recover/releases/tag/v0.1.0
