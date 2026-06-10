"""Unit tests for the synchronous updater module."""

from __future__ import annotations

import io
import json
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

from uzpr.updater.check import UpdateInfo, check_for_update, current_version


def _fake_response(payload: dict) -> io.BytesIO:
    buf = io.BytesIO(json.dumps(payload).encode("utf-8"))

    class _Ctx(io.BytesIO):
        def __enter__(self):  # type: ignore[override]
            return buf

        def __exit__(self, *a):  # type: ignore[override]
            return False

    return _Ctx()


def _release(tag: str = "v9.9.9", asset_name: str = "UZPR-Setup-9.9.9.exe") -> dict:
    return {
        "tag_name": tag,
        "body": "release notes",
        "assets": [
            {"name": asset_name, "browser_download_url": f"https://example/{asset_name}"},
        ],
    }


def test_current_version_returns_string():
    v = current_version()
    assert isinstance(v, str)
    assert v


def test_check_for_update_returns_info_when_newer(tmp_path: Path):
    settings = tmp_path / "settings.json"
    with patch("uzpr.updater.check.urllib.request.urlopen", return_value=_fake_response(_release())):
        info = check_for_update(settings_path=settings, now=1_000_000.0)

    assert isinstance(info, UpdateInfo)
    assert info.version == "9.9.9"
    assert info.installer_url.endswith(".exe")
    assert info.notes == "release notes"

    data = json.loads(settings.read_text())
    assert data["last_check_ts"] == 1_000_000.0
    assert data["last_update_info"]["version"] == "9.9.9"


def test_check_for_update_returns_none_when_not_newer(tmp_path: Path):
    settings = tmp_path / "settings.json"
    with patch(
        "uzpr.updater.check.urllib.request.urlopen",
        return_value=_fake_response(_release(tag="v0.0.1")),
    ):
        info = check_for_update(settings_path=settings, now=1_000_000.0)
    assert info is None


def test_check_for_update_throttled_within_24h(tmp_path: Path):
    settings = tmp_path / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    cached = {"version": "9.9.9", "notes": "cached", "installer_url": "https://example/x.exe"}
    settings.write_text(
        json.dumps({"last_check_ts": 1_000_000.0, "last_update_info": cached}),
    )

    with patch("uzpr.updater.check.urllib.request.urlopen") as m:
        info = check_for_update(settings_path=settings, now=1_000_000.0 + 60)
        m.assert_not_called()

    assert info is not None
    assert info.version == "9.9.9"
    assert info.notes == "cached"


def test_check_for_update_network_error_returns_none(tmp_path: Path):
    settings = tmp_path / "settings.json"
    with patch(
        "uzpr.updater.check.urllib.request.urlopen",
        side_effect=urllib.error.URLError("boom"),
    ):
        info = check_for_update(settings_path=settings, now=1_000_000.0)
    assert info is None


def test_check_for_update_disabled_returns_none(tmp_path: Path):
    settings = tmp_path / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps({"update_check_enabled": False}))

    with patch("uzpr.updater.check.urllib.request.urlopen") as m:
        info = check_for_update(settings_path=settings, now=1_000_000.0)
        m.assert_not_called()
    assert info is None


@pytest.mark.parametrize("missing", ["tag_name"])
def test_check_for_update_malformed_response(tmp_path: Path, missing: str):
    settings = tmp_path / "settings.json"
    payload = _release()
    payload.pop(missing)
    with patch(
        "uzpr.updater.check.urllib.request.urlopen",
        return_value=_fake_response(payload),
    ):
        info = check_for_update(settings_path=settings, now=1_000_000.0)
    assert info is None
