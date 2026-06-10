# Distribution

How UZPR ships to end users.

## Why winget

UZPR is distributed without an Authenticode code-signing certificate (those cost
~$300/year from a CA). Downloading the raw `UltimateZipPasswordRecover-Setup-x64.exe`
from GitHub Releases triggers a Microsoft SmartScreen warning until enough users
accept it to build reputation.

Installing via `winget` bypasses that friction:

```powershell
winget install LuisPCFialho.UltimateZipPasswordRecover
```

The Microsoft winget pipeline pulls the same binary, validates the sha256 against
the manifest we PR into [`microsoft/winget-pkgs`](https://github.com/microsoft/winget-pkgs),
and installs it as a trusted package. No warning.

It is also free.

## Release workflow (per version)

1. Bump `version` in `pyproject.toml`, `src/uzpr/__init__.py`, and `packaging/win/uzpr.iss`.
2. Update `CHANGELOG.md`.
3. `git commit -am "release: vX.Y.Z" && git tag vX.Y.Z && git push --tags`.
4. The `Release` GitHub Actions workflow builds the PyInstaller bundle, wraps it
   with Inno Setup, computes sha256, and publishes a GitHub Release.
5. Download the released installer locally into `dist/` (or let the workflow
   artifact land in `packaging/win/output/`).
6. Run the manifest renderer:
   ```powershell
   python scripts/winget/prepare_manifest.py
   ```
   This computes the real sha256 and writes the three YAML files into
   `packaging/winget/manifests/l/LuisPCFialho/UltimateZipPasswordRecover/<VERSION>/`.
7. **Manual:** open a PR against `microsoft/winget-pkgs`:
   - Fork `microsoft/winget-pkgs` once.
   - `git clone https://github.com/<you>/winget-pkgs`
   - Copy the rendered `<VERSION>/` folder into the same path inside the fork
     (`manifests/l/LuisPCFialho/UltimateZipPasswordRecover/<VERSION>/`).
   - Branch, commit, push, open PR titled `New version: LuisPCFialho.UltimateZipPasswordRecover <VERSION>`.
   - Wait for the Microsoft validation bot + a reviewer. Usually < 24h for
     existing publishers.

## Other channels (lower priority)

- **Scoop** — community bucket. We could submit to `extras` or maintain our own
  bucket at e.g. `LuisPCFialho/scoop-bucket`. Stretch goal; not blocking.
- **Chocolatey** — `community` repo requires manual moderation and a nuspec/PS
  install script. Lower priority than winget because it duplicates effort and
  reaches a smaller audience.

## Auto-update from inside the app

The app polls
`https://api.github.com/repos/LuisPCFialho/ultimate-zip-password-recover/releases/latest`
at most once per 24h (`src/uzpr/updater/check.py`). When a newer tag is found, the
UI offers to download the installer and launch it. Settings live in
`~/.uzpr/settings.json`:

```json
{
  "update_check_enabled": true,
  "last_check_ts": 1717977600.0,
  "last_update_info": { "version": "...", "notes": "...", "installer_url": "..." }
}
```

Users can disable the check by setting `update_check_enabled: false`.
