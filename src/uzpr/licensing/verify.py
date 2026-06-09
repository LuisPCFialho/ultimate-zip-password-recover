from __future__ import annotations

import base64
import json
import time
from enum import StrEnum
from typing import Any

from uzpr.util.logging import get_logger

log = get_logger(__name__)

# Token format (as per ARCHITECTURE.md §Monetization):
#   "<payload_b64>.<sig_b64>"
# payload JSON fields: id, email, sku, machine_fp, issued_at, expires_at | null, kid
#
# kid indexes into the embedded public key table.  During development the
# sentinel hex string "00"*32 means "no key configured — dev bypass".

_DEV_SENTINEL = "00" * 32

# Map kid -> Ed25519 public key hex.  Replace "00"*32 with the real key at
# release time (see ARCHITECTURE.md §Key rotation).
_PUBLIC_KEYS: dict[str, str] = {
    "1": _DEV_SENTINEL,
}


class LicenseStatus(StrEnum):
    VALID = "valid"
    EXPIRED = "expired"
    FORGED = "forged"
    MACHINE_MISMATCH = "machine_mismatch"
    MISSING = "missing"


class LicenseChecker:
    """Verifies a UZPR license token offline using Ed25519."""

    def verify_license(self, token_bytes: bytes) -> LicenseStatus:
        """Verify *token_bytes* and return the resulting :class:`LicenseStatus`.

        Token format::

            base64url(payload_json) + b"." + base64url(signature)

        where ``payload_json`` encodes the fields::

            {id, email, sku, machine_fp, issued_at, expires_at, kid}
        """
        if not token_bytes:
            return LicenseStatus.MISSING

        try:
            raw = token_bytes.strip()
            dot = raw.index(b".")
            payload_b64 = raw[:dot]
            sig_b64 = raw[dot + 1 :]
        except (ValueError, IndexError):
            log.warning("license_parse_failed", reason="missing dot separator")
            return LicenseStatus.FORGED

        try:
            payload_json = base64.urlsafe_b64decode(payload_b64 + b"==")
            payload: dict[str, Any] = json.loads(payload_json)
            signature = base64.urlsafe_b64decode(sig_b64 + b"==")
        except Exception as exc:
            log.warning("license_decode_failed", exc=str(exc))
            return LicenseStatus.FORGED

        kid: str = str(payload.get("kid", "1"))
        pubkey_hex: str = _PUBLIC_KEYS.get(kid, _DEV_SENTINEL)

        if pubkey_hex == _DEV_SENTINEL:
            log.warning(
                "license_key_not_configured",
                kid=kid,
                message="license key not configured — running in dev mode",
            )
            return LicenseStatus.VALID

        # Reconstruct canonical payload bytes the same way the server signed them.
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

        try:
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

            pubkey_bytes = bytes.fromhex(pubkey_hex)
            public_key: Ed25519PublicKey = Ed25519PublicKey.from_public_bytes(pubkey_bytes)
            public_key.verify(signature, canonical)
        except InvalidSignature:
            log.warning("license_signature_invalid", kid=kid)
            return LicenseStatus.FORGED
        except Exception as exc:
            log.warning("license_verify_error", exc=str(exc))
            return LicenseStatus.FORGED

        expires_at = payload.get("expires_at")
        if expires_at is not None and float(expires_at) < time.time():
            return LicenseStatus.EXPIRED

        from uzpr.licensing.fingerprint import machine_fingerprint

        stored_fp: str = str(payload.get("machine_fp", ""))
        if stored_fp and stored_fp != machine_fingerprint():
            log.warning("license_machine_mismatch", stored_fp=stored_fp)
            return LicenseStatus.MACHINE_MISMATCH

        return LicenseStatus.VALID
