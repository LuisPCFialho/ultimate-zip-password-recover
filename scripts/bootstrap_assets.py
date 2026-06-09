#!/usr/bin/env python3
"""Download wordlists and hashcat rules needed for packaging."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ASSETS: list[tuple[str, str]] = [
    (
        "https://raw.githubusercontent.com/danielmiessler/SecLists/master/"
        "Passwords/Common-Credentials/10k-most-common.txt",
        "packaging/wordlists/top10k.txt",
    ),
    (
        "https://raw.githubusercontent.com/hashcat/hashcat/master/rules/best66.rule",
        "packaging/rules/best66.rule",
    ),
    (
        "https://raw.githubusercontent.com/NotSoSecure/password_cracking_rules/master/"
        "OneRuleToRuleThemAll.rule",
        "packaging/rules/OneRuleToRuleThemAll.rule",
    ),
]


def _ensure_httpx() -> None:
    try:
        import httpx  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx"])


def download_assets(root: Path | None = None) -> None:
    import click
    import httpx

    if root is None:
        root = Path(__file__).parent.parent

    for url, rel_path in _ASSETS:
        dest = root / rel_path
        if dest.exists() and dest.stat().st_size > 0:
            click.echo(f"  skip  {dest.relative_to(root)}  (already exists)")
            continue

        dest.parent.mkdir(parents=True, exist_ok=True)
        click.echo(f"  fetch {url}")
        with httpx.Client(follow_redirects=True, timeout=60) as client:
            resp = client.get(url)
            resp.raise_for_status()
        dest.write_bytes(resp.content)
        size_kb = dest.stat().st_size / 1024
        click.echo(f"  saved {dest.relative_to(root)}  ({size_kb:.1f} KB)")


def main() -> None:
    _ensure_httpx()

    import click

    root = Path(__file__).parent.parent
    click.echo("Bootstrapping packaging assets...")
    download_assets(root)
    click.echo("Done.")


if __name__ == "__main__":
    main()
