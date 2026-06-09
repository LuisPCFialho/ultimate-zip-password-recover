from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

import anyio
import anyio.to_thread

from uzpr.util.logging import get_logger

log = get_logger(__name__)

_BENCHMARK_PATTERN = re.compile(r"^(\d+)\|.*\|(\d+)\|", re.MULTILINE)

# Stages whose engine is always 'native' regardless of GPU availability.
_NATIVE_ONLY_STAGES: frozenset[int] = frozenset({1})

# Archive formats that native verifier handles efficiently for small keyspaces.
_NATIVE_FORMATS: frozenset[str] = frozenset({"zip-classic", "rar3-hp"})

_SMALL_CANDIDATE_THRESHOLD = 1_000


@dataclass(slots=True)
class GpuDevice:
    id: int
    name: str
    vram_mb: int
    driver: str
    vendor: str  # 'nvidia'|'amd'|'intel'|'other'


class CapabilityProbe:
    """Detects GPU devices, probes hashcat support, and routes stages to engines."""

    def __init__(
        self,
        db_path: Path,
        hashcat_binary: Path | None = None,
    ) -> None:
        self._db_path = db_path
        self._hashcat_binary = hashcat_binary
        self._gpus: list[GpuDevice] = []
        self._benchmark_cache: dict[tuple[int, int], float] = {}
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _load_benchmark_cache(self) -> None:
        try:
            conn = self._get_conn()
            rows = conn.execute("SELECT device_key, benchmarks_json FROM capability_cache").fetchall()
            for row in rows:
                key_str: str = row["device_key"]
                benchmarks: dict[str, float] = json.loads(row["benchmarks_json"])
                # device_key format: "<mode>:<device_id>"
                parts = key_str.split(":", 1)
                if len(parts) == 2:
                    try:
                        mode = int(parts[0])
                        device_id = int(parts[1])
                        self._benchmark_cache[(mode, device_id)] = benchmarks.get("hps", 0.0)
                    except ValueError:
                        pass
        except Exception as exc:
            log.warning("benchmark_cache_load_failed", error=str(exc))

    def _save_benchmark(self, mode: int, device_id: int, hps: float, device_name: str, driver: str) -> None:
        try:
            conn = self._get_conn()
            device_key = f"{mode}:{device_id}"
            benchmarks_json = json.dumps({"hps": hps})
            now = time.time()
            conn.execute(
                """
                INSERT OR REPLACE INTO capability_cache
                    (device_key, device_name, driver_version, benchmarks_json, probed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (device_key, device_name, driver, benchmarks_json, now),
            )
            conn.commit()
        except Exception as exc:
            log.warning("benchmark_cache_save_failed", error=str(exc))

    def _parse_hashcat_devices(self, output: str) -> list[GpuDevice]:
        """Parse `hashcat -I` output into GpuDevice list."""
        devices: list[GpuDevice] = []
        device_id = 0
        current_name: str | None = None
        current_driver: str | None = None
        current_vram: int = 0
        current_vendor: str = "other"

        for line in output.splitlines():
            stripped = line.strip()
            id_match = re.match(r"^Backend Device ID #(\d+)", stripped)
            if id_match:
                if current_name is not None:
                    devices.append(GpuDevice(
                        id=device_id,
                        name=current_name,
                        vram_mb=current_vram,
                        driver=current_driver or "",
                        vendor=current_vendor,
                    ))
                device_id = int(id_match.group(1)) - 1  # hashcat is 1-indexed
                current_name = None
                current_driver = None
                current_vram = 0
                current_vendor = "other"
                continue
            if stripped.startswith("Name.."):
                current_name = stripped.split("..", 1)[-1].strip().lstrip(".")
            elif stripped.startswith("Driver Version"):
                current_driver = stripped.split(":", 1)[-1].strip()
            elif "Global Memory" in stripped:
                vram_match = re.search(r"(\d+)\s*MB", stripped)
                if vram_match:
                    current_vram = int(vram_match.group(1))
            elif stripped.startswith("Vendor"):
                vendor_str = stripped.split("..", 1)[-1].strip().lstrip(".")
                vendor_lower = vendor_str.lower()
                if "nvidia" in vendor_lower:
                    current_vendor = "nvidia"
                elif "amd" in vendor_lower or "advanced micro" in vendor_lower:
                    current_vendor = "amd"
                elif "intel" in vendor_lower:
                    current_vendor = "intel"
                else:
                    current_vendor = "other"

        if current_name is not None:
            devices.append(GpuDevice(
                id=device_id,
                name=current_name,
                vram_mb=current_vram,
                driver=current_driver or "",
                vendor=current_vendor,
            ))

        return devices

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def detect_gpus(self) -> list[GpuDevice]:
        """Detect GPU devices using system utilities and hashcat -I."""
        from uzpr.util import system as sys_util

        raw_gpus: list[dict[str, object]] = await anyio.to_thread.run_sync(sys_util.gpu_summary)

        # Build initial list from system info.
        gpus: list[GpuDevice] = []
        for idx, info in enumerate(raw_gpus):
            vendor_raw = str(info.get("vendor", "unknown")).lower()
            if "nvidia" in vendor_raw:
                vendor = "nvidia"
            elif "amd" in vendor_raw or "advanced micro" in vendor_raw:
                vendor = "amd"
            elif "intel" in vendor_raw:
                vendor = "intel"
            else:
                vendor = "other"
            gpus.append(GpuDevice(
                id=idx,
                name=str(info.get("name", f"GPU {idx}")),
                vram_mb=int(info.get("vram_mb", 0)),
                driver=str(info.get("driver", "")),
                vendor=vendor,
            ))

        # Cross-validate / supplement with hashcat -I if available.
        if self._hashcat_binary and self._hashcat_binary.is_file():
            try:
                result = await anyio.run_process(
                    [str(self._hashcat_binary), "-I"],
                    check=False,
                )
                hc_output = result.stdout.decode("utf-8", errors="replace")
                hc_gpus = self._parse_hashcat_devices(hc_output)
                if hc_gpus:
                    # Prefer hashcat's enumeration as it reflects actual OpenCL/CUDA backends.
                    gpus = hc_gpus
            except Exception as exc:
                log.debug("hashcat_device_probe_failed", error=str(exc))

        self._gpus = gpus
        self._load_benchmark_cache()
        log.info("gpus_detected", count=len(gpus), devices=[g.name for g in gpus])
        return gpus

    async def hashcat_capable(self, modes: list[int]) -> list[int]:
        """Return the subset of *modes* that hashcat can run on this machine."""
        if not self._hashcat_binary or not self._hashcat_binary.is_file():
            return []

        capable: list[int] = []
        device_id = self._gpus[0].id if self._gpus else 1

        for mode in modes:
            try:
                result = await anyio.run_process(
                    [
                        str(self._hashcat_binary),
                        "-b",
                        "-m", str(mode),
                        "--runtime=5",
                        "-O",
                        "-w", "2",
                        "-d", str(device_id),
                        "--machine-readable",
                    ],
                    check=False,
                )
                if result.returncode == 0:
                    capable.append(mode)
            except Exception as exc:
                log.debug("hashcat_mode_probe_failed", mode=mode, error=str(exc))

        return capable

    async def benchmark(self, mode: int, device_id: int) -> float:
        """Benchmark hashcat for *mode* on *device_id*, returning H/s.

        Result is cached in SQLite capability_cache table.
        """
        cache_key = (mode, device_id)
        if cache_key in self._benchmark_cache:
            return self._benchmark_cache[cache_key]

        if not self._hashcat_binary or not self._hashcat_binary.is_file():
            return 0.0

        hps = 0.0
        try:
            result = await anyio.run_process(
                [
                    str(self._hashcat_binary),
                    "-b",
                    "-m", str(mode),
                    "-d", str(device_id),
                    "--runtime=10",
                    "-O",
                    "-w", "2",
                    "--machine-readable",
                ],
                check=False,
            )
            output = result.stdout.decode("utf-8", errors="replace")
            match = _BENCHMARK_PATTERN.search(output)
            if match and int(match.group(1)) == mode:
                hps = float(match.group(2))
        except Exception as exc:
            log.debug("hashcat_benchmark_failed", mode=mode, device_id=device_id, error=str(exc))

        self._benchmark_cache[cache_key] = hps

        # Persist to SQLite.
        device_name = "unknown"
        driver = ""
        for gpu in self._gpus:
            if gpu.id == device_id:
                device_name = gpu.name
                driver = gpu.driver
                break
        self._save_benchmark(mode, device_id, hps, device_name, driver)

        return hps

    def choose_engine(self, stage_no: int, archive_format: str, candidate_count: int) -> str:
        """Select the best engine for a stage given the current capability profile.

        Returns one of: ``'native'``, ``'hashcat'``, ``'john'``.
        """
        if stage_no in _NATIVE_ONLY_STAGES:
            return "native"

        if candidate_count <= _SMALL_CANDIDATE_THRESHOLD and archive_format in _NATIVE_FORMATS:
            return "native"

        if self._gpus:
            return "hashcat"

        return "john"

    def get_gpu_ids(self) -> tuple[int, ...]:
        """Return a tuple of GPU device IDs detected on this machine."""
        return tuple(gpu.id for gpu in self._gpus)
