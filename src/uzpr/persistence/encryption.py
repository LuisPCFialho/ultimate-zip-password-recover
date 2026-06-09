from __future__ import annotations

from pathlib import Path


def dpapi_encrypt(plaintext: bytes) -> bytes:
    """Encrypt bytes with Windows DPAPI, fallback to Fernet if pywin32 unavailable."""
    try:
        import win32crypt

        _desc, ciphertext = win32crypt.CryptProtectData(plaintext, None, None, None, None, 0)
        return ciphertext
    except ImportError:
        return _fernet_encrypt(plaintext)


def dpapi_decrypt(ciphertext: bytes) -> bytes:
    """Decrypt bytes with Windows DPAPI, fallback to Fernet if pywin32 unavailable."""
    try:
        import win32crypt

        _desc, plaintext = win32crypt.CryptUnprotectData(ciphertext, None, None, None, 0)
        return plaintext
    except ImportError:
        return _fernet_decrypt(ciphertext)


def _fernet_key() -> bytes:
    import platformdirs

    key_path = Path(platformdirs.user_data_dir("UltimateZipPasswordRecover", False)) / "fernet.key"
    if not key_path.exists():
        from uzpr.util.logging import get_logger

        log = get_logger(__name__)
        log.warning("DPAPI unavailable; falling back to Fernet key storage", key_path=str(key_path))
        from cryptography.fernet import Fernet

        key_path.parent.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        key_path.write_bytes(key)
        return key
    return key_path.read_bytes()


def _fernet_encrypt(plaintext: bytes) -> bytes:
    from cryptography.fernet import Fernet

    return Fernet(_fernet_key()).encrypt(plaintext)


def _fernet_decrypt(ciphertext: bytes) -> bytes:
    from cryptography.fernet import Fernet

    return Fernet(_fernet_key()).decrypt(ciphertext)
