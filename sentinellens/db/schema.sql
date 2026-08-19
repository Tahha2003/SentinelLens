-- ═══════════════════════════════════════════════════════════════════════════════
-- sentinellens.db  —  SQLite Schema v1.0
-- Run:  sqlite3 sentinellens.db < sentinellens/db/schema.sql
-- ═══════════════════════════════════════════════════════════════════════════════

-- PRAGMA SETTINGS  (applied on every connection open by repository.py)
PRAGMA journal_mode = WAL;      -- concurrent reads during pipeline writes
PRAGMA foreign_keys = ON;       -- CRITICAL: cascade deletes need this per-connection
PRAGMA synchronous  = NORMAL;   -- safe with WAL; faster than FULL
PRAGMA cache_size   = -32000;   -- 32 MB page cache (negative = kilobytes)
PRAGMA temp_store   = MEMORY;   -- temp tables in RAM — faster sorts on feature queries

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: pipeline_runs
-- Tracks every pipeline execution. Created first — clusters FK to it.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id              TEXT PRIMARY KEY,  -- UUID4, returned immediately on POST /pipeline/run
    status              TEXT NOT NULL CHECK(status IN ('queued','running','complete','failed')),
    datasource_mode     TEXT NOT NULL CHECK(datasource_mode IN ('local_bots','splunk_live')),
    event_count         INTEGER DEFAULT NULL,
    normalized_count    INTEGER DEFAULT NULL,
    cluster_count       INTEGER DEFAULT NULL,
    normalization_failures INTEGER DEFAULT 0,
    error_message       TEXT    DEFAULT NULL,
    started_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    completed_at        TEXT    DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_runs_status     ON pipeline_runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON pipeline_runs(started_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: events
-- All normalized security events. Written once per pipeline run, never updated.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS events (
    event_id    TEXT PRIMARY KEY,
    timestamp   TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    entity_type TEXT NOT NULL CHECK(entity_type IN ('USER','HOST','IP','PROCESS','URL','UNKNOWN')),
    event_type  TEXT NOT NULL,
    severity    INTEGER NOT NULL CHECK(severity BETWEEN 1 AND 5),
    source      TEXT NOT NULL,
    raw_fields  TEXT NOT NULL,   -- JSON blob
    tags        TEXT NOT NULL DEFAULT '[]',  -- JSON array
    ingested_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_events_entity_id  ON events(entity_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp  ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_severity   ON events(severity);
CREATE INDEX IF NOT EXISTS idx_events_source     ON events(source);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: incident_clusters
-- One row per cluster from the correlation engine.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS incident_clusters (
    cluster_id      TEXT PRIMARY KEY,
    time_start      TEXT NOT NULL,
    time_end        TEXT NOT NULL,
    entities        TEXT NOT NULL,   -- JSON array of entity_ids
    features        TEXT NOT NULL,   -- JSON object: IncidentFeatures
    is_truncated    INTEGER NOT NULL DEFAULT 0,
    pipeline_run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_clusters_time_start ON incident_clusters(time_start);
CREATE INDEX IF NOT EXISTS idx_clusters_pipeline   ON incident_clusters(pipeline_run_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: cluster_events  (many-to-many join)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cluster_events (
    cluster_id TEXT NOT NULL REFERENCES incident_clusters(cluster_id) ON DELETE CASCADE,
    event_id   TEXT NOT NULL REFERENCES events(event_id)              ON DELETE CASCADE,
    PRIMARY KEY (cluster_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_ce_cluster_id ON cluster_events(cluster_id);
CREATE INDEX IF NOT EXISTS idx_ce_event_id   ON cluster_events(event_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: scored_incidents
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scored_incidents (
    incident_id     TEXT PRIMARY KEY,
    cluster_id      TEXT NOT NULL UNIQUE REFERENCES incident_clusters(cluster_id) ON DELETE CASCADE,
    score           REAL NOT NULL CHECK(score >= 0.0 AND score <= 1.0),
    confidence_band TEXT NOT NULL CHECK(confidence_band IN ('HIGH','MEDIUM','LOW')),
    model_version   TEXT NOT NULL,
    label           INTEGER DEFAULT NULL,
    scored_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_si_score        ON scored_incidents(score DESC);
CREATE INDEX IF NOT EXISTS idx_si_confidence   ON scored_incidents(confidence_band);
CREATE INDEX IF NOT EXISTS idx_si_model_version ON scored_incidents(model_version);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: investigation_sessions  (Phase 2)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS investigation_sessions (
    session_id      TEXT PRIMARY KEY,
    incident_id     TEXT NOT NULL REFERENCES scored_incidents(incident_id) ON DELETE CASCADE,
    status          TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','complete','failed')),
    analyst_query   TEXT NOT NULL,
    spl_generated   TEXT DEFAULT NULL,
    result_raw      TEXT DEFAULT NULL,
    result_summary  TEXT DEFAULT NULL,
    agent_backend   TEXT DEFAULT NULL CHECK(agent_backend IN ('mcp_server','splunk_sdk','local_mock',NULL)),
    error_message   TEXT DEFAULT NULL,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    completed_at    TEXT DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_inv_incident_id ON investigation_sessions(incident_id);
CREATE INDEX IF NOT EXISTS idx_inv_status      ON investigation_sessions(status);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: model_registry
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS model_registry (
    model_id         TEXT PRIMARY KEY,   -- SHA256 of .joblib artifact
    algorithm        TEXT NOT NULL CHECK(algorithm IN ('logistic_regression','gradient_boosting')),
    dataset          TEXT NOT NULL,
    feature_set      TEXT NOT NULL,      -- JSON array of feature names
    precision_val    REAL DEFAULT NULL,
    recall_val       REAL DEFAULT NULL,
    f1_val           REAL DEFAULT NULL,
    confusion_matrix TEXT DEFAULT NULL,  -- JSON: [[TN,FP],[FN,TP]]
    artifact_path    TEXT NOT NULL,
    trained_at       TEXT NOT NULL,
    is_active        INTEGER NOT NULL DEFAULT 0  -- exactly ONE row with is_active=1 at all times
);
