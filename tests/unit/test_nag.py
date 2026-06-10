"""Unit tests for the nag dialog logic (no Qt required)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from uzpr.util.settings_store import SettingsStore


def _make_store(tmp_path: Path, **kwargs) -> SettingsStore:
    store = SettingsStore(path=tmp_path / "settings.json")
    for k, v in kwargs.items():
        store.set(k, v)
    return store


# ---------------------------------------------------------------------------
# maybe_show_nag — skip conditions
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_skip_when_pro(tmp_path: Path) -> None:
    """maybe_show_nag must not show anything when is_pro() returns True."""
    store = _make_store(tmp_path)

    with patch("uzpr.ui.nag.is_pro", return_value=True):
        with patch("uzpr.ui.nag.NagDialog") as mock_dlg:
            from uzpr.ui.nag import maybe_show_nag

            maybe_show_nag(parent=None, store=store)
            mock_dlg.assert_not_called()


@pytest.mark.unit
def test_skip_when_shown_today(tmp_path: Path) -> None:
    """maybe_show_nag must not show anything when last_nag_at is today."""
    today = date.today().isoformat()
    store = _make_store(tmp_path, last_nag_at=today)

    with patch("uzpr.ui.nag.is_pro", return_value=False):
        with patch("uzpr.ui.nag.NagDialog") as mock_dlg:
            from uzpr.ui.nag import maybe_show_nag

            maybe_show_nag(parent=None, store=store)
            mock_dlg.assert_not_called()


@pytest.mark.unit
def test_shows_when_conditions_met(tmp_path: Path) -> None:
    """maybe_show_nag must instantiate and exec NagDialog when not Pro and not shown today."""
    store = _make_store(tmp_path, last_nag_at="1970-01-01")

    mock_instance = MagicMock()
    mock_instance.exec.return_value = 0

    with patch("uzpr.ui.nag.is_pro", return_value=False):
        with patch("uzpr.ui.nag.NagDialog", return_value=mock_instance) as mock_cls:
            from uzpr.ui.nag import maybe_show_nag

            maybe_show_nag(parent=None, store=store)
            mock_cls.assert_called_once()
            mock_instance.exec.assert_called_once()


@pytest.mark.unit
def test_shows_when_no_previous_nag(tmp_path: Path) -> None:
    """maybe_show_nag must show when last_nag_at is absent."""
    store = _make_store(tmp_path)  # no last_nag_at key

    mock_instance = MagicMock()
    mock_instance.exec.return_value = 0

    with patch("uzpr.ui.nag.is_pro", return_value=False):
        with patch("uzpr.ui.nag.NagDialog", return_value=mock_instance):
            from uzpr.ui.nag import maybe_show_nag

            maybe_show_nag(parent=None, store=store)
            mock_instance.exec.assert_called_once()
