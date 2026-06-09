from __future__ import annotations

import math
import mmap
import sqlite3
import struct
import time
from pathlib import Path

from uzpr.util.hashing import blake3_trunc16


class BloomFilter:
    """Memory-mapped bloom filter for candidate deduplication.

    Uses two independent 64-bit hash values derived from blake3_trunc16 to
    simulate k independent hash functions via double-hashing:
        h_i(x) = (h1 + i * h2) mod m
    """

    def __init__(self, path: Path, capacity: int, fp_rate: float = 0.001) -> None:
        """Open or create a bloom filter file at *path*.

        Args:
            path: File path for the mmap-backed bit array.
            capacity: Expected number of distinct items (n).
            fp_rate: Target false-positive probability (p).
        """
        ln2 = math.log(2)
        # Optimal bit-array size: m = -n * ln(p) / (ln2)^2
        m_bits = math.ceil(-capacity * math.log(fp_rate) / (ln2 ** 2))
        # Optimal number of hash functions: k = (m / n) * ln2
        self._k = max(1, round((m_bits / capacity) * ln2))
        self._m = m_bits
        self._byte_size = math.ceil(m_bits / 8)

        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(b"\x00" * self._byte_size)
        else:
            # Extend file if existing file is smaller than required.
            existing = path.stat().st_size
            if existing < self._byte_size:
                with path.open("ab") as fh:
                    fh.write(b"\x00" * (self._byte_size - existing))

        self._fh = path.open("r+b")
        self._mm = mmap.mmap(self._fh.fileno(), self._byte_size)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _hashes(self, candidate: str) -> list[int]:
        """Return k bit positions for *candidate* using double-hashing."""
        raw: bytes = blake3_trunc16(candidate)
        # Split 16 bytes into two 64-bit unsigned ints.
        h1, h2 = struct.unpack_from(">QQ", raw, 0)
        # Ensure h2 is odd to guarantee full-cycle coverage.
        h2 = h2 | 1
        return [(h1 + i * h2) % self._m for i in range(self._k)]

    def _set_bit(self, pos: int) -> None:
        byte_idx, bit_idx = divmod(pos, 8)
        self._mm[byte_idx] = self._mm[byte_idx] | (1 << bit_idx)

    def _test_bit(self, pos: int) -> bool:
        byte_idx, bit_idx = divmod(pos, 8)
        return bool(self._mm[byte_idx] & (1 << bit_idx))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add(self, candidate: str) -> None:
        """Set all k bits for *candidate* in the bit array."""
        for pos in self._hashes(candidate):
            self._set_bit(pos)

    def __contains__(self, candidate: object) -> bool:
        """Return True if *candidate* may have been added (possible false positive)."""
        if not isinstance(candidate, str):
            return False
        return all(self._test_bit(pos) for pos in self._hashes(candidate))

    def close(self) -> None:
        """Flush and release the mmap and file handle."""
        self._mm.flush()
        self._mm.close()
        self._fh.close()


class TriedCandidateStore:
    """SQLite-backed store for crash-safe candidate deduplication.

    Uses a WITHOUT ROWID table keyed on the blake3 truncated hash so that
    recovery after a crash is exact (no false positives unlike the bloom filter).
    Intended for use from a single synchronous context only.
    """

    _DDL = """
        CREATE TABLE IF NOT EXISTS tried_candidates (
            hash_blake3         BLOB PRIMARY KEY,
            first_seen_stage    INTEGER NOT NULL,
            ts                  REAL NOT NULL
        ) WITHOUT ROWID;
    """

    def __init__(self, db_path: Path) -> None:
        """Open or create the SQLite database at *db_path*.

        Args:
            db_path: File path for the SQLite database.
        """
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute(self._DDL)

    def add_batch(self, candidates: list[str], stage_no: int) -> None:
        """Insert a batch of candidates, ignoring duplicates.

        Args:
            candidates: Plain-text candidate strings to record.
            stage_no: Stage number that generated these candidates.
        """
        now = time.time()
        rows = [
            (blake3_trunc16(c), stage_no, now)
            for c in candidates
        ]
        self._conn.executemany(
            "INSERT OR IGNORE INTO tried_candidates (hash_blake3, first_seen_stage, ts) "
            "VALUES (?, ?, ?)",
            rows,
        )

    def contains(self, candidate: str) -> bool:
        """Return True if *candidate* has been recorded in this store."""
        h = blake3_trunc16(candidate)
        row = self._conn.execute(
            "SELECT 1 FROM tried_candidates WHERE hash_blake3 = ? LIMIT 1", (h,)
        ).fetchone()
        return row is not None

    def close(self) -> None:
        """Close the underlying database connection."""
        self._conn.close()
