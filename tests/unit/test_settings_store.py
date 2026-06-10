"""Unit tests for SettingsStore."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from uzpr.util.settings_store import SettingsStore


@pytest.fixture()
def tmp_store(tmp_path: Path) -> SettingsStore:
    return SettingsStore(path=tmp_path / "settings.json")


@pytest.mark.unit
def test_get_default_when_missing(tmp_store: SettingsStore) -> None:
    assert tmp_store.get("nonexistent", "fallback") == "fallback"


@pytest.mark.unit
def test_get_none_default(tmp_store: SettingsStore) -> None:
    assert tmp_store.get("missing") is None


@pytest.mark.unit
def test_set_and_get_round_trip(tmp_store: SettingsStore) -> None:
    tmp_store.set("launch_count", 5)
    assert tmp_store.get("launch_count") == 5


@pytest.mark.unit
def test_save_persists_to_disk(tmp_path: Path) -> None:
    store = SettingsStore(path=tmp_path / "settings.json")
    store.set("last_nag_at", "2025-01-01")
    store.save()

    data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert data["last_nag_at"] == "2025-01-01"


@pytest.mark.unit
def test_reload_from_existing_file(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")

    store = SettingsStore(path=p)
    assert store.get("foo") == "bar"


@pytest.mark.unit
def test_save_creates_parent_dirs(tmp_path: Path) -> None:
    store = SettingsStore(path=tmp_path / "nested" / "dir" / "settings.json")
    store.set("x", 1)
    store.save()
    assert (tmp_path / "nested" / "dir" / "settings.json").exists()


@pytest.mark.unit
def test_corrupt_file_treated_as_empty(tmp_path: Path) -> None:
    p = tmp_path / "settings.json"
    p.write_text("not json", encoding="utf-8")
    store = SettingsStore(path=p)
    assert store.get("any", "default") == "default"
