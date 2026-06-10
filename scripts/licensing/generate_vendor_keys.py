"""Generate the offline vendor Ed25519 keypair.

Run ONCE. The private key is written to ``~/.uzpr-vendor/private_key.pem`` and
must never enter the repository. The public key hex is printed to stdout; paste
it into ``src/uzpr/licensing/keys.py``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> int:
    vendor_dir = Path(os.path.expanduser("~")) / ".uzpr-vendor"
    priv_path = vendor_dir / "private_key.pem"

    if priv_path.exists():
        print(f"refusing to overwrite existing private key: {priv_path}", file=sys.stderr)
        return 1

    vendor_dir.mkdir(parents=True, exist_ok=True)

    private_key = Ed25519PrivateKey.generate()
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    priv_path.write_bytes(pem)
    try:
        os.chmod(priv_path, 0o600)
    except OSError:
        pass

    public_key = private_key.public_key()
    pub_hex = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    ).hex()

    print(f"private key written to: {priv_path}")
    print("public key (paste into src/uzpr/licensing/keys.py VENDOR_PUBLIC_KEY_HEX):")
    print(pub_hex)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
