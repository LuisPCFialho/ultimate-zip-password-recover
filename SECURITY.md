# Security Policy

## Intended use

Ultimate ZIP Password Recover is a tool for recovering passwords on archives **you own** or for which you have **explicit written authorization to access**. Using the tool against archives you do not own or are not authorized to access is illegal in most jurisdictions and a violation of these terms.

The first-run dialog requires confirmation of ownership before any cracking session starts. Sessions are logged locally for auditability.

## Reporting a vulnerability

If you discover a security vulnerability in the application itself (not a cracking-engine issue), please report it privately via GitHub Security Advisories on the repository, or by email to the maintainer listed in [`README.md`](README.md). Please do not open a public issue for security problems.

We aim to acknowledge within 72 hours and patch high-severity issues within 14 days.

## Supported versions

| Version | Supported |
|---------|-----------|
| `0.x`   | Active development; latest minor receives fixes |

## What we treat as a vulnerability

- Code injection paths through user-supplied archive filenames or passwords.
- Memory disclosure of recovered passwords (we encrypt at rest via the OS keyring).
- Privilege escalation through the bundled engine binaries.
- Use of unverified third-party binaries — every bundled binary is checksum-verified at install and runtime.

## What we do not treat as a vulnerability

- The fact that the tool can recover passwords. That is the purpose.
- Slow performance on specific hardware (this is a performance issue; please open a regular issue).
- Engine-specific crashes in hashcat, John the Ripper, or bkcrack — please report those upstream.
