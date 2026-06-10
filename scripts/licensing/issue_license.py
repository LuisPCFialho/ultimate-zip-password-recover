"""Issue a signed UZPR license token.

Usage::

    python scripts/licensing/issue_license.py --email buyer@example.com \
        --tier pro [--machine-id <hex>]

The token is printed to stdout. Email it to the buyer.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii").rstrip("=")


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue a UZPR license token")
    parser.add_argument("--email", required=True)
    parser.add_argument("--tier", default="pro")
    parser.add_argument("--machine-id", default=None, help="optional machine fingerprint")
    parser.add_argument(
        "--key",
        default=str(Path(os.path.expanduser("~")) / ".uzpr-vendor" / "private_key.pem"),
    )
    args = parser.parse_args()

    key_path = Path(args.key)
    if not key_path.exists():
        print(f"private key not found: {key_path}", file=sys.stderr)
        print("run scripts/licensing/generate_vendor_keys.py first", file=sys.stderr)
        return 1

    private_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    if not isinstance(private_key, Ed25519PrivateKey):
        print("loaded key is not Ed25519", file=sys.stderr)
        return 1

    payload = {
        "email": args.email,
        "tier": args.tier,
        "issued_at": int(time.time()),
        "machine_id": args.machine_id,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = private_key.sign(payload_bytes)

    token = f"{_b64(payload_bytes)}.{_b64(signature)}"
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
