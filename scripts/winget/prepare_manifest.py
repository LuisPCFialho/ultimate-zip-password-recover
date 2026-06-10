"""Render winget manifests for the current release.

Reads version from ``pyproject.toml``, computes sha256 of the local installer
at ``dist/UZPR-Setup-<VERSION>.exe`` (or the Inno Setup output path), and
writes the three manifest YAMLs into
``packaging/winget/manifests/l/LuisPCFialho/UltimateZipPasswordRecover/<VERSION>/``.

After running, manually:
  1. git clone https://github.com/<you>/winget-pkgs (fork of microsoft/winget-pkgs)
  2. Copy the rendered <VERSION>/ folder into the same path under that repo.
  3. git checkout -b add-uzpr-<VERSION> && commit && push && open PR.
"""

from __future__ import annotations

import hashlib
import sys
from datetime import date
from pathlib import Path

try:
    import tomllib  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - py<3.11
    import tomli as tomllib  # type: ignore[no-redef]

REPO = Path(__file__).resolve().parents[2]
PYPROJECT = REPO / "pyproject.toml"
MANIFEST_ROOT = REPO / "packaging" / "winget" / "manifests" / "l" / "LuisPCFialho" / "UltimateZipPasswordRecover"

INSTALLER_CANDIDATES = (
    "dist/UZPR-Setup-{version}.exe",
    "packaging/win/output/UltimateZipPasswordRecover-Setup-x64.exe",
)

RELEASE_URL_TMPL = (
    "https://github.com/LuisPCFialho/ultimate-zip-password-recover/releases/download/"
    "v{version}/UltimateZipPasswordRecover-Setup-x64.exe"
)


def _read_version() -> str:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _find_installer(version: str) -> Path:
    for tmpl in INSTALLER_CANDIDATES:
        p = REPO / tmpl.format(version=version)
        if p.exists():
            return p
    raise FileNotFoundError(
        f"installer not found; tried: {[t.format(version=version) for t in INSTALLER_CANDIDATES]}"
    )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def _render(version: str, sha: str, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    (out_dir / "LuisPCFialho.UltimateZipPasswordRecover.yaml").write_text(
        "# yaml-language-server: $schema=https://aka.ms/winget-manifest.version.1.6.0.schema.json\n"
        "PackageIdentifier: LuisPCFialho.UltimateZipPasswordRecover\n"
        f"PackageVersion: {version}\n"
        "DefaultLocale: en-US\n"
        "ManifestType: version\n"
        "ManifestVersion: 1.6.0\n",
        encoding="utf-8",
    )

    (out_dir / "LuisPCFialho.UltimateZipPasswordRecover.installer.yaml").write_text(
        "# yaml-language-server: $schema=https://aka.ms/winget-manifest.installer.1.6.0.schema.json\n"
        "PackageIdentifier: LuisPCFialho.UltimateZipPasswordRecover\n"
        f"PackageVersion: {version}\n"
        "InstallerType: inno\n"
        "Scope: user\n"
        "InstallModes:\n"
        "  - interactive\n"
        "  - silent\n"
        "  - silentWithProgress\n"
        "UpgradeBehavior: install\n"
        f"ReleaseDate: {today}\n"
        "Installers:\n"
        "  - Architecture: x64\n"
        f"    InstallerUrl: {RELEASE_URL_TMPL.format(version=version)}\n"
        f"    InstallerSha256: {sha}\n"
        "ManifestType: installer\n"
        "ManifestVersion: 1.6.0\n",
        encoding="utf-8",
    )

    (out_dir / "LuisPCFialho.UltimateZipPasswordRecover.locale.en-US.yaml").write_text(
        "# yaml-language-server: $schema=https://aka.ms/winget-manifest.defaultLocale.1.6.0.schema.json\n"
        "PackageIdentifier: LuisPCFialho.UltimateZipPasswordRecover\n"
        f"PackageVersion: {version}\n"
        "PackageLocale: en-US\n"
        "Publisher: Luis Fialho\n"
        "PublisherUrl: https://github.com/LuisPCFialho\n"
        "PublisherSupportUrl: https://github.com/LuisPCFialho/ultimate-zip-password-recover/issues\n"
        "PackageName: Ultimate ZIP Password Recover\n"
        "PackageUrl: https://github.com/LuisPCFialho/ultimate-zip-password-recover\n"
        "License: MIT\n"
        "LicenseUrl: https://github.com/LuisPCFialho/ultimate-zip-password-recover/blob/main/LICENSE\n"
        "ShortDescription: ZipCrypto / WinZip AES / RAR password recovery — free and open source\n"
        "Tags:\n"
        "  - zip\n"
        "  - password\n"
        "  - rar\n"
        "  - recovery\n"
        "  - security\n"
        "ManifestType: defaultLocale\n"
        "ManifestVersion: 1.6.0\n",
        encoding="utf-8",
    )


def main() -> int:
    version = _read_version()
    installer = _find_installer(version)
    sha = _sha256(installer)
    out_dir = MANIFEST_ROOT / version
    _render(version, sha, out_dir)

    print(f"Rendered winget manifests for {version}")
    print(f"  installer: {installer}")
    print(f"  sha256:    {sha}")
    print(f"  output:    {out_dir}")
    print()
    print("Next steps:")
    print("  1. Fork microsoft/winget-pkgs on GitHub if you haven't.")
    print("  2. git clone https://github.com/<your-fork>/winget-pkgs")
    print(f"  3. Copy {out_dir} → winget-pkgs/manifests/l/LuisPCFialho/UltimateZipPasswordRecover/{version}/")
    print(f"  4. cd winget-pkgs && git checkout -b add-uzpr-{version}")
    print('  5. git commit -m "New version: LuisPCFialho.UltimateZipPasswordRecover {version}" && git push')
    print("  6. Open PR against microsoft/winget-pkgs:main and wait for moderation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
