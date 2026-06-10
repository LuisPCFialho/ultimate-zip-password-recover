"""Self-signed license token verification (Ed25519).

Token format::

    base64(payload_json) + "." + base64(signature)

payload JSON::

    {"email": str, "tier": str, "issued_at": int, "machine_id": str | null}

When ``machine_id`` is non-null the token is bound to that machine.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from uzpr.licensing import keys
from uzpr.licensing.machine_id import get_machine_id


@dataclass(frozen=True)
class License:
    email: str
    tier: str
    issued_at: int
    machine_id: str | None


def _license_path() -> Path:
    return Path(os.path.expanduser("~")) / ".uzpr" / "license.txt"


def _b64decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.b64decode(data + pad)


def verify_license(token: str) -> License | None:
    """Verify *token* signature with the embedded vendor public key.

    Returns the decoded :class:`License` on success, ``None`` otherwise.
    """
    token = token.strip()
    if not token or "." not in token:
        return None

    try:
        payload_b64, sig_b64 = token.split(".", 1)
        payload_bytes = _b64decode(payload_b64)
        signature = _b64decode(sig_b64)
    except (ValueError, binascii.Error):
        return None

    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        pubkey = Ed25519PublicKey.from_public_bytes(bytes.fromhex(keys.VENDOR_PUBLIC_KEY_HEX))
        pubkey.verify(signature, payload_bytes)
    except (InvalidSignature, ValueError):
        return None
    except Exception:
        return None

    try:
        payload: dict[str, Any] = json.loads(payload_bytes)
        lic = License(
            email=str(payload["email"]),
            tier=str(payload["tier"]),
            issued_at=int(payload["issued_at"]),
            machine_id=payload["machine_id"] if payload.get("machine_id") is not None else None,
        )
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return None

    if lic.machine_id is not None and lic.machine_id != get_machine_id():
        return None

    return lic


def install_license(token: str, path: Path | None = None) -> Path:
    """Validate *token* and persist it to the license store. Returns the path."""
    if verify_license(token) is None:
        raise ValueError("invalid license token")
    target = path if path is not None else _license_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(token.strip() + "\n", encoding="utf-8")
    return target


def load_license(path: Path | None = None) -> License | None:
    """Load and verify the first valid token from the license file."""
    target = path if path is not None else _license_path()
    if not target.exists():
        return None
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        lic = verify_license(line)
        if lic is not None:
            return lic
    return None


def is_pro(path: Path | None = None) -> bool:
    """Return ``True`` when a valid ``tier == "pro"`` license is installed."""
    lic = load_license(path)
    return lic is not None and lic.tier == "pro"
