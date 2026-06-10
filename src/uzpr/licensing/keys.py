"""Embedded vendor public key for license verification.

The matching private key is held offline by the vendor and never enters this
repository. See docs/LICENSING.md for the key-issuance workflow.
"""

from __future__ import annotations

# TODO: Replace with the real vendor public key (64 hex chars / 32 bytes)
# produced by `python scripts/licensing/generate_vendor_keys.py`.
VENDOR_PUBLIC_KEY_HEX: str = "0" * 64
