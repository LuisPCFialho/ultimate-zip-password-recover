from __future__ import annotations

"""CLI entry point: uzpr-cli command for scripting and headless use."""

import asyncio
import sys
from pathlib import Path

import click

from uzpr.util.logging import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------


@click.group()
def main() -> None:
    """Ultimate ZIP Password Recover — command-line interface."""


# ---------------------------------------------------------------------------
# crack
# ---------------------------------------------------------------------------


@main.command()
@click.argument("archive", type=click.Path(exists=True, path_type=Path))
@click.option("--password", "-p", default=None, help="Try this password first.")
@click.option("--hint-date", multiple=True, help="Known date (DD/MM/YYYY).")
@click.option("--hint-stem", multiple=True, help="Known word/stem in the password.")
@click.option(
    "--budget",
    default=3600,
    type=int,
    show_default=True,
    help="Total time budget in seconds.",
)
@click.option("--low-power", is_flag=True, default=False, help="Limit GPU power usage.")
def crack(
    archive: Path,
    password: str | None,
    hint_date: tuple[str, ...],
    hint_stem: tuple[str, ...],
    budget: int,
    low_power: bool,
) -> None:
    """Run the cascade attack on ARCHIVE."""
    dates = _parse_hint_dates(hint_date)
    asyncio.run(_run_crack(archive, password, dates, hint_stem, budget, low_power))


def _parse_hint_dates(
    raw_dates: tuple[str, ...],
) -> tuple[tuple[int, int, int], ...]:
    """Parse DD/MM/YYYY strings into (d, m, y) int-tuples."""
    parsed: list[tuple[int, int, int]] = []
    for raw in raw_dates:
        try:
            parts = raw.split("/")
            if len(parts) != 3:
                raise ValueError("expected DD/MM/YYYY")
            d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
            parsed.append((d, m, y))
        except ValueError as exc:
            click.echo(f"[uzpr] Warning: ignoring invalid date '{raw}': {exc}", err=True)
    return tuple(parsed)


async def _run_crack(
    archive: Path,
    password: str | None,
    dates: tuple[tuple[int, int, int], ...],
    stems: tuple[str, ...],
    budget: int,
    low_power: bool,
) -> None:
    from uzpr.app import build_application
    from uzpr.core.stages.protocol import Hints

    hints = Hints(
        full_password=password,
        dates=dates,
        stems=stems,
    )

    orchestrator = build_application()

    from uzpr.archive.detect import detect_archive
    from uzpr.util.paths import db_path

    archive_info = detect_archive(archive)

    from uzpr.persistence.repo import SessionRepo

    repo = SessionRepo(db_path=db_path())
    session_id = await repo.create_session(
        archive_info=archive_info,
        hints=hints,
        total_budget_s=float(budget),
        gpu_low_power=low_power,
    )

    def on_event_sync(event: object) -> None:
        click.echo(str(event), err=True)

    async def on_event(event: object) -> None:
        on_event_sync(event)

    result = await orchestrator.run_session(session_id, on_event)

    if result.password:
        click.echo(result.password)
    else:
        click.echo(f"[uzpr] Password not found. Outcome: {result.outcome}", err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------


@main.command()
def tools() -> None:
    """Show status of bundled tools (hashcat, john, bkcrack)."""
    try:
        from uzpr.engines.tool_manager import ToolStatus, list_status
    except ImportError as exc:
        click.echo(f"[uzpr] Cannot import tool_manager: {exc}", err=True)
        sys.exit(1)

    statuses: list[ToolStatus] = list_status()

    _print_tools_table(statuses)


def _print_tools_table(statuses: list[object]) -> None:
    """Print tool statuses as a rich table, falling back to plain text."""
    try:
        from rich.console import Console
        from rich.table import Table

        table = Table(title="Bundled Tools", show_header=True, header_style="bold cyan")
        table.add_column("Tool", style="bold")
        table.add_column("Status")
        table.add_column("Version")
        table.add_column("Path")

        for s in statuses:
            table.add_row(
                str(getattr(s, "name", "?")),
                str(getattr(s, "status", "?")),
                str(getattr(s, "version", "?")),
                str(getattr(s, "path", "?")),
            )

        Console().print(table)

    except ImportError:
        click.echo(f"{'Tool':<16} {'Status':<12} {'Version':<12} Path")
        click.echo("-" * 60)
        for s in statuses:
            click.echo(
                f"{getattr(s, 'name', '?'):<16} "
                f"{getattr(s, 'status', '?'):<12} "
                f"{getattr(s, 'version', '?'):<12} "
                f"{getattr(s, 'path', '?')}"
            )


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


@main.command()
def version() -> None:
    """Print version and exit."""
    import uzpr

    click.echo(uzpr.__version__)
