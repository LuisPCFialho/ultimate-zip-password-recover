"""Synchronous GitHub Releases update check with persistent 24h throttle."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_FALLBACK_VERSION = "0.1.0"
_RELEASES_URL = (
    "https://api.github.com/repos/LuisPCFialho/ultimate-zip-password-recover/releases/latest"
)
_THROTTLE_SECONDS = 24 * 60 * 60
_SETTINGS_PATH = Path.home() / ".uzpr" / "settings.json"


@dataclass(frozen=True, slots=True)
class UpdateInfo:
    version: str
    notes: str
    installer_url: str


def current_version() -> str:
    """Return the installed package version, falling back to a constant."""
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("ultimate-zip-password-recover")
        except PackageNotFoundError:
            return _FALLBACK_VERSION
    except Exception:
        return _FALLBACK_VERSION


def _load_settings(path: Path = _SETTINGS_PATH) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_settings(data: dict, path: Path = _SETTINGS_PATH) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as exc:
        log.warning("settings_write_failed: %s", exc)


def _cached_info(settings: dict) -> UpdateInfo | None:
    raw = settings.get("last_update_info")
    if not isinstance(raw, dict):
        return None
    try:
        return UpdateInfo(
            version=str(raw["version"]),
            notes=str(raw["notes"]),
            installer_url=str(raw["installer_url"]),
        )
    except KeyError:
        return None


def check_for_update(
    timeout: float = 5.0,
    *,
    settings_path: Path = _SETTINGS_PATH,
    now: float | None = None,
) -> UpdateInfo | None:
    """Return :class:`UpdateInfo` if a newer release exists, else *None*.

    Honors ``update_check_enabled`` and throttles to once per 24h via
    ``last_check_ts`` in ``settings_path``. Network errors return *None*.
    """
    settings = _load_settings(settings_path)
    if settings.get("update_check_enabled", True) is False:
        return None

    now_ts = time.time() if now is None else now
    last_ts = float(settings.get("last_check_ts", 0) or 0)
    if now_ts - last_ts < _THROTTLE_SECONDS:
        return _cached_info(settings)

    current = current_version()
    info: UpdateInfo | None = None
    try:
        req = urllib.request.Request(
            _RELEASES_URL,
            headers={"User-Agent": f"uzpr/{current}", "Accept": "application/vnd.github+json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))

        tag = str(data.get("tag_name", "")).lstrip("v")
        if not tag:
            raise ValueError("missing tag_name")

        from packaging.version import InvalidVersion, Version

        try:
            if Version(tag) <= Version(current):
                info = None
            else:
                installer_url = ""
                for asset in data.get("assets", []) or []:
                    name = str(asset.get("name", ""))
                    if name.lower().endswith(".exe"):
                        installer_url = str(asset.get("browser_download_url", ""))
                        break
                info = UpdateInfo(
                    version=tag,
                    notes=str(data.get("body", "")),
                    installer_url=installer_url,
                )
        except InvalidVersion as exc:
            log.warning("update_check_bad_version: %s", exc)
            info = None

    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, OSError) as exc:
        log.warning("update_check_failed: %s", exc)
        return None

    settings["last_check_ts"] = now_ts
    settings["last_update_info"] = asdict(info) if info is not None else None
    _save_settings(settings, settings_path)
    return info
