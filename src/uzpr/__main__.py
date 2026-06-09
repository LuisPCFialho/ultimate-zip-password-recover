"""Entry point — `python -m uzpr` and the `uzpr` script both land here."""

from __future__ import annotations

import sys


def main() -> int:
    """Launch the Ultimate ZIP Password Recover desktop application."""
    try:
        from uzpr.ui.app import run_gui
    except ImportError as exc:
        print(f"GUI dependencies not available: {exc}", file=sys.stderr)
        print("Install with: pip install ultimate-zip-password-recover[gui]", file=sys.stderr)
        return 1

    return run_gui(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
