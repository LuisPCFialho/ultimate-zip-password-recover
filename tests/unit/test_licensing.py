"""Unit tests for self-signed Ed25519 license tokens."""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from uzpr.licensing import keys, license as lic_mod
from uzpr.licensing.license import install_license, is_pro, load_license, verify_license


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii").rstrip("=")


def _make_token(
    private_key: Ed25519PrivateKey,
    *,
    email: str = "buyer@example.com",
    tier: str = "pro",
    issued_at: int | None = None,
    machine_id: str | None = None,
) -> str:
    payload = {
        "email": email,
        "tier": tier,
        "issued_at": issued_at if issued_at is not None else int(time.time()),
        "machine_id": machine_id,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = private_key.sign(payload_bytes)
    return f"{_b64(payload_bytes)}.{_b64(signature)}"


@pytest.fixture()
def test_keypair(monkeypatch: pytest.MonkeyPatch) -> Ed25519PrivateKey:
    from cryptography.hazmat.primitives import serialization

    private_key = Ed25519PrivateKey.generate()
    pub_hex = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        .hex()
    )
    monkeypatch.setattr(keys, "VENDOR_PUBLIC_KEY_HEX", pub_hex)
    return private_key


def test_verify_roundtrip(test_keypair: Ed25519PrivateKey) -> None:
    token = _make_token(test_keypair, email="luis@example.com")
    result = verify_license(token)
    assert result is not None
    assert result.email == "luis@example.com"
    assert result.tier == "pro"
    assert result.machine_id is None


def test_tampered_token_rejected(test_keypair: Ed25519PrivateKey) -> None:
    token = _make_token(test_keypair)
    payload_b64, sig_b64 = token.split(".", 1)
    tampered_payload = _b64(b'{"email":"attacker@example.com","tier":"pro","issued_at":0,"machine_id":null}')
    tampered = f"{tampered_payload}.{sig_b64}"
    assert verify_license(tampered) is None


def test_wrong_public_key_rejected(
    test_keypair: Ed25519PrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _make_token(test_keypair)
    # Swap public key to a different one
    other_key = Ed25519PrivateKey.generate()
    from cryptography.hazmat.primitives import serialization

    other_hex = (
        other_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        .hex()
    )
    monkeypatch.setattr(keys, "VENDOR_PUBLIC_KEY_HEX", other_hex)
    assert verify_license(token) is None


def test_machine_id_mismatch_rejected(
    test_keypair: Ed25519PrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(lic_mod, "get_machine_id", lambda: "deadbeef")
    token = _make_token(test_keypair, machine_id="cafebabe")
    assert verify_license(token) is None


def test_machine_id_match_accepted(
    test_keypair: Ed25519PrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(lic_mod, "get_machine_id", lambda: "deadbeef")
    token = _make_token(test_keypair, machine_id="deadbeef")
    result = verify_license(token)
    assert result is not None
    assert result.machine_id == "deadbeef"


def test_install_and_load(test_keypair: Ed25519PrivateKey, tmp_path: Path) -> None:
    token = _make_token(test_keypair)
    path = tmp_path / "license.txt"
    install_license(token, path=path)
    assert path.exists()
    loaded = load_license(path=path)
    assert loaded is not None
    assert loaded.tier == "pro"


def test_install_rejects_invalid(test_keypair: Ed25519PrivateKey, tmp_path: Path) -> None:
    path = tmp_path / "license.txt"
    with pytest.raises(ValueError):
        install_license("not-a-real-token", path=path)
    assert not path.exists()


def test_is_pro_no_file(tmp_path: Path) -> None:
    assert is_pro(path=tmp_path / "missing.txt") is False


def test_is_pro_true_when_installed(test_keypair: Ed25519PrivateKey, tmp_path: Path) -> None:
    token = _make_token(test_keypair, tier="pro")
    path = tmp_path / "license.txt"
    install_license(token, path=path)
    assert is_pro(path=path) is True


def test_is_pro_false_for_non_pro_tier(
    test_keypair: Ed25519PrivateKey, tmp_path: Path
) -> None:
    token = _make_token(test_keypair, tier="free")
    path = tmp_path / "license.txt"
    install_license(token, path=path)
    assert is_pro(path=path) is False


def test_garbage_token_returns_none(test_keypair: Ed25519PrivateKey) -> None:
    assert verify_license("") is None
    assert verify_license("no-dot-here") is None
    assert verify_license("!!!.???") is None
