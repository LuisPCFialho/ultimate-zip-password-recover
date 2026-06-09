PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA wal_autocheckpoint = 1000;

CREATE TABLE sessions (
    id              TEXT PRIMARY KEY,
    archive_path    TEXT NOT NULL,
    archive_sha256  TEXT NOT NULL,
    archive_format  TEXT NOT NULL,
    hashcat_mode    INTEGER,
    total_budget_s  REAL NOT NULL,
    hints_json      BLOB NOT NULL,
    status          TEXT NOT NULL,
    gpu_low_power   INTEGER NOT NULL DEFAULT 0,
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
);
CREATE INDEX idx_sessions_archive ON sessions(archive_sha256);
CREATE INDEX idx_sessions_status ON sessions(status);

CREATE TABLE stages (
    id                  TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    stage_no            INTEGER NOT NULL,
    name                TEXT NOT NULL,
    engine              TEXT NOT NULL,
    status              TEXT NOT NULL,
    budget_s            REAL NOT NULL,
    prior_p             REAL NOT NULL,
    candidates_tested   INTEGER NOT NULL DEFAULT 0,
    elapsed_s           REAL NOT NULL DEFAULT 0,
    restore_token       TEXT,
    last_heartbeat_at   REAL,
    failure_count       INTEGER NOT NULL DEFAULT 0,
    UNIQUE(session_id, stage_no)
);
CREATE INDEX idx_stages_status ON stages(status);

CREATE TABLE attempts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    stage_id            TEXT NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
    started_at          REAL NOT NULL,
    ended_at            REAL,
    outcome             TEXT,
    candidates_tested   INTEGER NOT NULL DEFAULT 0,
    peak_rate           REAL
);
CREATE INDEX idx_attempts_session ON attempts(session_id);

CREATE TABLE results (
    session_id          TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    password            TEXT NOT NULL,
    found_by_stage_id   TEXT NOT NULL REFERENCES stages(id),
    found_at            REAL NOT NULL,
    bkcrack_keys        TEXT
);

CREATE TABLE events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id          TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    stage_id            TEXT REFERENCES stages(id) ON DELETE CASCADE,
    ts                  REAL NOT NULL,
    level               TEXT NOT NULL,
    payload_json        TEXT NOT NULL
);
CREATE INDEX idx_events_session_ts ON events(session_id, ts);

CREATE TABLE tried_candidates (
    hash_blake3         BLOB PRIMARY KEY,
    first_seen_stage    INTEGER NOT NULL,
    ts                  REAL NOT NULL
) WITHOUT ROWID;

CREATE TABLE capability_cache (
    device_key          TEXT PRIMARY KEY,
    device_name         TEXT NOT NULL,
    driver_version      TEXT NOT NULL,
    benchmarks_json     TEXT NOT NULL,
    probed_at           REAL NOT NULL
);
