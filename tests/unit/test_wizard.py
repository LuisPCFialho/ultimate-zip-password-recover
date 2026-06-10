"""Smoke test for the Simple/Advanced wizard."""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.mark.unit
def test_wizard_module_imports() -> None:
    """The wizard module must import cleanly and expose its public API.

    Full widget instantiation requires an interactive Qt platform — the
    offscreen platform blocks indefinitely on qfluentwidgets label
    construction in this environment, so we only verify the import surface
    here.  Luis should launch the app manually to smoke-test the UI.
    """
    from uzpr.ui import wizard

    assert hasattr(wizard, "WizardWindow")
    assert hasattr(wizard, "SimpleModeWidget")
    assert wizard.MODE_SIMPLE == "simple"
    assert wizard.MODE_ADVANCED == "advanced"
    mode = wizard.load_preferred_mode()
    assert mode in (wizard.MODE_SIMPLE, wizard.MODE_ADVANCED)


@pytest.mark.unit
def test_date_parser() -> None:
    from uzpr.ui.wizard import _parse_dates

    assert _parse_dates("14/02/1990, 25/12/2010") == ((14, 2, 1990), (25, 12, 2010))
    assert _parse_dates("invalid") == ()
    assert _parse_dates("31/02/2020") == ()  # invalid calendar date
