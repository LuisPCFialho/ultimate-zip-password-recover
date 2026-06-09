from __future__ import annotations

"""Fetch bundled wordlists and hashcat rule files into the packaging/ tree.

Usage::

    python scripts/fetch_wordlists.py fetch top10k
    python scripts/fetch_wordlists.py fetch rockyou --i-agree
    python scripts/fetch_wordlists.py fetch rules
"""

import tarfile
from pathlib import Path

import click
import httpx

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPTS_DIR.parent
_WORDLISTS_DIR = _PROJECT_ROOT / "packaging" / "wordlists"
_RULES_DIR = _PROJECT_ROOT / "packaging" / "rules"

# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------

_TOP10K_URL = (
    "https://raw.githubusercontent.com/danielmiessler/SecLists/master/"
    "Passwords/Common-Credentials/10-million-password-list-top-10000.txt"
)
_ROCKYOU_URL = (
    "https://github.com/danielmiessler/SecLists/raw/master/"
    "Passwords/Leaked-Databases/rockyou.txt.tar.gz"
)

_RULE_SOURCES: dict[str, str] = {
    "OneRuleToRuleThemAll.rule": (
        "https://raw.githubusercontent.com/NotSoSecure/password_cracking_rules/"
        "master/OneRuleToRuleThemAll.rule"
    ),
    "best64.rule": ("https://raw.githubusercontent.com/hashcat/hashcat/master/rules/best64.rule"),
    "dive.rule": ("https://raw.githubusercontent.com/hashcat/hashcat/master/rules/dive.rule"),
}

_ROCKYOU_LICENSE_NOTICE = """\
NOTICE — rockyou.txt license
==============================
The rockyou.txt wordlist originates from the 2009 RockYou data breach.
Its redistribution is legally ambiguous and potentially restricted in some
jurisdictions.  By passing --i-agree you confirm that you accept sole
responsibility for the legal implications of downloading and using this file,
and that you are not redistributing it to third parties.
"""

_CHUNK_SIZE = 65_536  # 64 KiB


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stream_download(url: str, dest: Path, label: str) -> None:
    """Stream-download *url* to *dest*, printing a progress indicator."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    downloaded = 0

    with httpx.stream("GET", url, follow_redirects=True, timeout=60.0) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))

        with dest.open("wb") as fh:
            for chunk in response.iter_bytes(chunk_size=_CHUNK_SIZE):
                fh.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    click.echo(
                        f"\r[fetch] {label}: {downloaded:,} / {total:,} bytes  ({pct}%)",
                        nl=False,
                        err=True,
                    )
                else:
                    click.echo(
                        f"\r[fetch] {label}: {downloaded:,} bytes",
                        nl=False,
                        err=True,
                    )

    click.echo(f"\r[fetch] {label}: {downloaded:,} bytes — done.            ", err=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.group()
def cli() -> None:
    """Fetch bundled wordlists and rule files for UZPR packaging."""


@cli.group()
def fetch() -> None:
    """Download a specific asset."""


@fetch.command("top10k")
def fetch_top10k() -> None:
    """Download the top-10 000 passwords from SecLists (freely redistributable)."""
    dest = _WORDLISTS_DIR / "top10k.txt"
    _stream_download(_TOP10K_URL, dest, "top10k.txt")
    click.echo(f"Saved to: {dest}")


@fetch.command("rockyou")
@click.option(
    "--i-agree",
    "i_agree",
    is_flag=True,
    default=False,
    help="Confirm you accept the license terms before downloading.",
)
def fetch_rockyou(i_agree: bool) -> None:
    """Download and extract rockyou.txt (requires --i-agree due to license terms)."""
    click.echo(_ROCKYOU_LICENSE_NOTICE)
    if not i_agree:
        click.echo(
            "Aborted. Re-run with --i-agree to confirm you accept the license terms.",
            err=True,
        )
        raise SystemExit(1)

    archive_tmp = _WORDLISTS_DIR / "rockyou.txt.tar.gz"
    dest = _WORDLISTS_DIR / "rockyou.txt"

    _stream_download(_ROCKYOU_URL, archive_tmp, "rockyou.txt.tar.gz")

    click.echo("[fetch] Extracting rockyou.txt …", err=True)
    with tarfile.open(archive_tmp, "r:gz") as tf:
        member = next(
            (m for m in tf.getmembers() if m.name.endswith("rockyou.txt")),
            None,
        )
        if member is None:
            raise click.ClickException("rockyou.txt not found inside the archive.")
        extracted = tf.extractfile(member)
        if extracted is None:
            raise click.ClickException("Could not read rockyou.txt from archive.")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(extracted.read())

    archive_tmp.unlink(missing_ok=True)
    click.echo(f"Extracted to: {dest}  ({dest.stat().st_size:,} bytes)")


@fetch.command("rules")
def fetch_rules() -> None:
    """Download OneRuleToRuleThemAll, best64, and dive hashcat rule files."""
    _RULES_DIR.mkdir(parents=True, exist_ok=True)

    for filename, url in _RULE_SOURCES.items():
        dest = _RULES_DIR / filename
        _stream_download(url, dest, filename)
        size = dest.stat().st_size
        click.echo(f"Saved {filename}: {size:,} bytes → {dest}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
