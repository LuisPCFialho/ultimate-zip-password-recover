from __future__ import annotations

import platform
import subprocess
import sys

import psutil


def cpu_info() -> dict[str, object]:
    """Return CPU model, thread count, and base frequency via py-cpuinfo."""
    try:
        import cpuinfo  # type: ignore[import-untyped]

        info = cpuinfo.get_cpu_info()
        return {
            "model": info.get("brand_raw", platform.processor()) or platform.processor(),
            "threads": info.get("count", 0),
            "freq_mhz": (
                float(info.get("hz_advertised_friendly", "0 MHz").split()[0])
                if "hz_advertised_friendly" in info
                else 0.0
            ),
        }
    except Exception:
        freq = psutil.cpu_freq()
        return {
            "model": platform.processor(),
            "threads": psutil.cpu_count(logical=True) or 0,
            "freq_mhz": float(freq.max) if freq else 0.0,
        }


def is_battery() -> bool:
    """Return True when the system is running on battery (not plugged in)."""
    try:
        battery = psutil.sensors_battery()
        if battery is None:
            return False
        return not battery.power_plugged
    except Exception:
        return False


def _parse_nvidia_smi() -> list[dict[str, object]]:
    """Query nvidia-smi and parse GPU rows; raises on failure."""
    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return []
    gpus: list[dict[str, object]] = []
    for line in result.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        try:
            vram = int(parts[1])
        except ValueError:
            vram = 0
        gpus.append({"name": parts[0], "vram_mb": vram, "driver": parts[2], "vendor": "nvidia"})
    return gpus


def _parse_wmic() -> list[dict[str, object]]:
    """Fall back to wmic for GPU info; raises on failure."""
    result = subprocess.run(
        ["wmic", "path", "win32_VideoController", "get", "Name,AdapterRAM", "/format:csv"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return []
    gpus: list[dict[str, object]] = []
    lines = [ln for ln in result.stdout.strip().splitlines() if ln.strip()]
    # First non-empty line is the header: Node,AdapterRAM,Name
    if not lines:
        return []
    header = [h.strip().lower() for h in lines[0].split(",")]
    try:
        name_idx = header.index("name")
        ram_idx = header.index("adapterram")
    except ValueError:
        return []
    for line in lines[1:]:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) <= max(name_idx, ram_idx):
            continue
        name = parts[name_idx]
        if not name:
            continue
        try:
            vram_bytes = int(parts[ram_idx])
            vram_mb = vram_bytes // (1024 * 1024)
        except ValueError:
            vram_mb = 0
        gpus.append({"name": name, "vram_mb": vram_mb, "driver": "", "vendor": "unknown"})
    return gpus


def gpu_summary() -> list[dict[str, object]]:
    """Return a list of GPU info dicts; tries nvidia-smi then wmic; empty on failure."""
    if sys.platform != "win32":
        return []

    try:
        gpus = _parse_nvidia_smi()
        if gpus:
            return gpus
    except Exception:
        pass

    try:
        return _parse_wmic()
    except Exception:
        return []
