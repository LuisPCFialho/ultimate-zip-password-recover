from __future__ import annotations

#!/usr/bin/env python3
"""Create test fixture archives for integration tests."""
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import pyzipper  # type: ignore[import-untyped]

FIXTURES = Path(__file__).parent


def create_zipcrypto_archive() -> Path:
    """Create a small ZipCrypto-style encrypted ZIP with password 'test123'.

    Uses AES-256 (WZ_AES) since pyzipper does not support writing classic
    ZipCrypto (stream-cipher) archives.  The NativeVerifier handles both
    zip-classic and zip-aes via pyzipper.AESZipFile, so AES fixtures are
    sufficient for stage integration tests.
    """
    path = FIXTURES / "test_zipcrypto.zip"
    with pyzipper.AESZipFile(
        path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        encryption=pyzipper.WZ_AES,
    ) as zf:
        zf.setpassword(b"test123")
        zf.writestr("hello.txt", "Hello, World! This is a test file.")
    return path


def create_aes_archive() -> Path:
    """Create a small WinZip AES-256 encrypted ZIP with password 'abc123'."""
    path = FIXTURES / "test_aes256.zip"
    with pyzipper.AESZipFile(
        path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        encryption=pyzipper.WZ_AES,
        allowZip64=True,
    ) as zf:
        zf.setpassword(b"abc123")
        zf.writestr("secret.txt", "Secret content for testing AES-256 encryption.")
    return path


if __name__ == "__main__":
    FIXTURES.mkdir(parents=True, exist_ok=True)
    p1 = create_zipcrypto_archive()
    print(f"Created: {p1} ({p1.stat().st_size} bytes)")
    p2 = create_aes_archive()
    print(f"Created: {p2} ({p2.stat().st_size} bytes)")
    print("Done.")
