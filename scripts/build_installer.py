#!/usr/bin/env python3
"""Build UZPR installer: bootstrap assets -> PyInstaller -> Inno Setup."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

_ISCC_PATHS = [
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
]


def _check_python_version() -> None:
    import click

    if sys.version_info < (3, 11):  # noqa: UP036
        click.echo(
            f"ERROR: Python >= 3.11 required, got {sys.version_info.major}.{sys.version_info.minor}",
            err=True,
        )
        sys.exit(1)
    click.echo(f"Python {sys.version_info.major}.{sys.version_info.minor} OK")


def _ensure_pyinstaller() -> None:
    import click

    try:
        import PyInstaller  # noqa: F401

        click.echo("PyInstaller already installed")
    except ImportError:
        click.echo("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def _find_iscc() -> Path | None:
    for p in _ISCC_PATHS:
        if p.exists():
            return p
    return None


def _run_pyinstaller() -> None:
    import click

    spec = ROOT / "packaging" / "win" / "uzpr.spec"
    dist = ROOT / "dist"
    work = ROOT / "build" / "pyinstaller"

    click.echo(f"\nRunning PyInstaller with spec: {spec}")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            str(spec),
            "--distpath",
            str(dist),
            "--workpath",
            str(work),
            "--noconfirm",
        ],
        cwd=ROOT,
    )
    if result.returncode != 0:
        click.echo("ERROR: PyInstaller failed", err=True)
        sys.exit(result.returncode)
    click.echo("PyInstaller build complete")


def _run_inno_setup(iscc: Path) -> None:
    import click

    iss = ROOT / "packaging" / "win" / "uzpr.iss"
    click.echo(f"\nRunning Inno Setup: {iscc}")
    result = subprocess.run([str(iscc), str(iss)], cwd=ROOT)
    if result.returncode != 0:
        click.echo("ERROR: Inno Setup failed", err=True)
        sys.exit(result.returncode)

    output_dir = ROOT / "packaging" / "win" / "output"
    exes = list(output_dir.glob("*.exe"))
    if exes:
        for exe in exes:
            size_mb = exe.stat().st_size / (1024 * 1024)
            click.echo(f"  Installer: {exe}  ({size_mb:.1f} MB)")
    click.echo("Inno Setup build complete")


def main() -> None:
    import click

    _check_python_version()

    # Step 1: bootstrap assets
    click.echo("\n--- Bootstrapping assets ---")
    sys.path.insert(0, str(Path(__file__).parent))
    from bootstrap_assets import download_assets

    download_assets(ROOT)

    # Step 2: create icon (idempotent)
    ico_path = ROOT / "packaging" / "win" / "uzpr.ico"
    if not ico_path.exists():
        click.echo("\n--- Creating icon ---")
        import create_icon

        create_icon.main()
    else:
        click.echo(f"\nIcon exists: {ico_path}")

    # Step 3: ensure PyInstaller
    click.echo("\n--- Checking PyInstaller ---")
    _ensure_pyinstaller()

    # Step 4: run PyInstaller
    click.echo("\n--- PyInstaller bundle ---")
    _run_pyinstaller()

    # Step 5: Inno Setup
    iscc = _find_iscc()
    if iscc is None:
        click.echo(
            "\nInno Setup not found. Download from:\n"
            "  https://jrsoftware.org/isdl.php\n"
            "Then re-run this script.\n"
            "Expected locations:\n" + "\n".join(f"  {p}" for p in _ISCC_PATHS)
        )
    else:
        click.echo("\n--- Inno Setup installer ---")
        _run_inno_setup(iscc)

    click.echo("\nBuild complete.")


if __name__ == "__main__":
    main()
