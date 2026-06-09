from __future__ import annotations

from pathlib import Path

from uzpr.archive.detect import RarEntry


def list_rar_entries(path: Path) -> list[RarEntry]:
    """List entries in a RAR archive using rarfile."""
    try:
        import rarfile  # type: ignore[import-untyped]

        entries: list[RarEntry] = []
        with rarfile.RarFile(path) as rf:
            for info in rf.infolist():
                entries.append(
                    RarEntry(
                        name=info.filename,
                        size=info.file_size,
                        compressed_size=info.compress_size,
                        encrypted=info.needs_password(),
                    )
                )
        return entries
    except Exception:
        return []
