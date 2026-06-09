from __future__ import annotations

from dataclasses import dataclass

import httpx

from uzpr.util.logging import get_logger

log = get_logger(__name__)

_RELEASES_URL = (
    "https://api.github.com/repos/LuisPCFialho/ultimate-zip-password-recover/releases/latest"
)
_TIMEOUT_SECONDS = 10.0
_RELEASE_NOTES_MAX_CHARS = 500


@dataclass(frozen=True, slots=True)
class UpdateInfo:
    latest_version: str
    download_url: str
    release_notes: str


class UpdateChecker:
    """Check GitHub Releases for a newer version of UZPR."""

    async def check_for_updates(self) -> UpdateInfo | None:
        """Return :class:`UpdateInfo` if a newer release exists, else *None*.

        Returns *None* on any network or parse error so callers can treat this
        as a best-effort, non-blocking operation.
        """
        try:
            import uzpr

            current: str = uzpr.__version__

            async with httpx.AsyncClient(
                timeout=_TIMEOUT_SECONDS,
                headers={"User-Agent": f"uzpr/{current}"},
                follow_redirects=True,
            ) as client:
                response = await client.get(_RELEASES_URL)
                response.raise_for_status()
                data: dict[str, object] = response.json()

            tag_name: str = str(data["tag_name"]).lstrip("v")

            from packaging.version import Version

            if Version(tag_name) <= Version(current):
                return None

            # Find the first Windows installer asset.
            assets: list[dict[str, object]] = list(data.get("assets", []))  # type: ignore[arg-type]
            download_url: str = ""
            for asset in assets:
                name = str(asset.get("name", ""))
                if name.endswith(".exe"):
                    download_url = str(asset.get("browser_download_url", ""))
                    break

            body: str = str(data.get("body", ""))[:_RELEASE_NOTES_MAX_CHARS]

            return UpdateInfo(
                latest_version=tag_name,
                download_url=download_url,
                release_notes=body,
            )

        except (httpx.HTTPError, KeyError, ValueError) as exc:
            log.warning("update_check_failed", exc=str(exc))
            return None
