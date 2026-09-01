# SPDX-License-Identifier: MIT
"""
SentinelLens database repository.

ALL database operations go through this class.
No other module touches the DB directly.
All queries are parameterized — zero string concatenation for SQL values.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = _BASE_DIR / "schema.sql"
DEFAULT_DB_PATH = Path("sentinellens.db")


class Repository:
    MAX_RETRIES = 3
    RETRY_DELAY_SECS = 0.1

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self._db_path = db_path
        self._init_db()

    # ── Internal helpers ───────────────────────────────────────────────────────

    @contextmanager
    def _connect(self):
        """
        Context manager for a single SQLite connection.
        Commits on clean exit, rolls back on exception.
        timeout=30 lets SQLite itself serialize concurrent writers — no retry loop needed.
        """
        conn = sqlite3.connect(str(self._db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Apply schema DDL. Safe to call on every startup (CREATE IF NOT EXISTS)."""
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        with self._connect() as conn:
            conn.executescript(schema)
        logger.debug("Database schema applied: %s", self._db_path)

    # ── Pipeline Runs ──────────────────────────────────────────────────────────

    def save_pipeline_run(self, run_id: str, datasource_mode: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO pipeline_runs (run_id, status, datasource_mode) VALUES (?,?,?)",
                (run_id, "queued", datasource_mode),
            )

    def update_pipeline_run(self, run_id: str, **kwargs: Any) -> None:
        if not kwargs:
            return
        cols = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [run_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE pipeline_runs SET {cols} WHERE run_id = ?", vals)  # noqa: S608

    def get_pipeline_run(self, run_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM pipeline_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_recent_runs(self, limit: int = 10) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ── Events ─────────────────────────────────────────────────────────────────

    def insert_events(self, events) -> int:
        """
        Batch insert events. Skips duplicates (INSERT OR IGNORE).
        Returns number of rows actually inserted.
        """
        rows = [e.to_db_row() for e in events]
        with self._connect() as conn:
            conn.executemany(
                """INSERT OR IGNORE INTO events
                   (event_id, timestamp, entity_id, entity_type, event_type,
                    severity, source, raw_fields, tags)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                rows,
            )
            return conn.total_changes

    # ── Clusters ───────────────────────────────────────────────────────────────

    def insert_cluster(self, cluster) -> None:
        """
        Atomically insert an IncidentCluster and all its cluster_events links.
        Both succeed or both roll back.
        """
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO incident_clusters
                   (cluster_id, time_start, time_end, entities, features,
                    is_truncated, pipeline_run_id)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    cluster.cluster_id,
                    cluster.time_start.isoformat(),
                    cluster.time_end.isoformat(),
                    json.dumps(sorted(cluster.entities)),
                    json.dumps(cluster.features.to_dict()),
                    int(cluster.is_truncated),
                    cluster.pipeline_run_id,
                ),
            )
            conn.executemany(
                "INSERT OR IGNORE INTO cluster_events (cluster_id, event_id) VALUES (?,?)",
                [(cluster.cluster_id, e.event_id) for e in cluster.events],
            )

    # ── Scored Incidents ───────────────────────────────────────────────────────

    def insert_scored_incident(self, si) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO scored_incidents
                   (incident_id, cluster_id, score, confidence_band, model_version, label)
                   VALUES (?,?,?,?,?,?)""",
                (
                    si.incident_id,
                    si.cluster.cluster_id,
                    si.score,
                    si.confidence_band,
                    si.model_version,
                    si.label,
                ),
            )

    def get_incidents(
        self,
        page: int = 1,
        limit: int = 20,
        min_score: float = 0.0,
        band: Optional[str] = None,
    ) -> tuple[list[dict], int]:
        """
        Return paginated list of scored incidents joined with cluster data.
        Returns (rows, total_count).
        """
        offset = (page - 1) * limit
        params: list[Any] = [min_score]
        band_clause = ""
        if band:
            band_clause = "AND si.confidence_band = ?"
            params.append(band)

        count_params = list(params)
        count_sql = f"""
            SELECT COUNT(*) FROM scored_incidents si
            WHERE si.score >= ? {band_clause}
        """  # noqa: S608

        sql = f"""
            SELECT
                si.incident_id, si.score, si.confidence_band,
                si.model_version, si.scored_at,
                ic.cluster_id, ic.time_start, ic.time_end,
                ic.entities, ic.is_truncated,
                json_extract(ic.features,'$.event_count')     AS event_count,
                json_extract(ic.features,'$.severity_max')    AS severity_max,
                json_extract(ic.features,'$.entity_fan_out')  AS entity_fan_out,
                json_extract(ic.features,'$.time_span_minutes') AS time_span_minutes
            FROM scored_incidents si
            JOIN incident_clusters ic ON si.cluster_id = ic.cluster_id
            WHERE si.score >= ? {band_clause}
            ORDER BY si.score DESC
            LIMIT ? OFFSET ?
        """  # noqa: S608
        params.extend([limit, offset])

        with self._connect() as conn:
            total = conn.execute(count_sql, count_params).fetchone()[0]
            rows = conn.execute(sql, params).fetchall()

        return [dict(r) for r in rows], total

    def get_incident_by_id(self, incident_id: str) -> Optional[dict]:
        sql = """
            SELECT
                si.incident_id, si.score, si.confidence_band,
                si.model_version, si.scored_at, si.label,
                ic.cluster_id, ic.time_start, ic.time_end,
                ic.entities, ic.features, ic.is_truncated
            FROM scored_incidents si
            JOIN incident_clusters ic ON si.cluster_id = ic.cluster_id
            WHERE si.incident_id = ?
        """  # noqa: S608
        with self._connect() as conn:
            row = conn.execute(sql, (incident_id,)).fetchone()
        return dict(row) if row else None

    def get_timeline(self, incident_id: str) -> list[dict]:
        """Return all events for an incident ordered by timestamp."""
        sql = """
            SELECT e.*
            FROM events e
            JOIN cluster_events ce ON e.event_id = ce.event_id
            JOIN scored_incidents si ON si.cluster_id = ce.cluster_id
            WHERE si.incident_id = ?
            ORDER BY e.timestamp ASC
        """  # noqa: S608
        with self._connect() as conn:
            rows = conn.execute(sql, (incident_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_incident_features(self, incident_id: str) -> Optional[dict]:
        sql = """
            SELECT ic.features
            FROM incident_clusters ic
            JOIN scored_incidents si ON si.cluster_id = ic.cluster_id
            WHERE si.incident_id = ?
        """  # noqa: S608
        with self._connect() as conn:
            row = conn.execute(sql, (incident_id,)).fetchone()
        if not row:
            return None
        return json.loads(row["features"])

    # ── Investigation Sessions ─────────────────────────────────────────────────

    def save_investigation(self, session_id: str, incident_id: str, analyst_query: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO investigation_sessions
                   (session_id, incident_id, analyst_query, status)
                   VALUES (?,?,?,'queued')""",
                (session_id, incident_id, analyst_query),
            )

    def update_investigation(self, session_id: str, **kwargs: Any) -> None:
        if not kwargs:
            return
        cols = ", ".join(f"{k} = ?" for k in kwargs)
        vals = list(kwargs.values()) + [session_id]
        with self._connect() as conn:
            conn.execute(
                f"UPDATE investigation_sessions SET {cols} WHERE session_id = ?", vals  # noqa: S608
            )

    def get_investigation(self, session_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM investigation_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return dict(row) if row else None

    # ── Model Registry ─────────────────────────────────────────────────────────

    def register_model(
        self,
        model_id: str,
        algorithm: str,
        dataset: str,
        feature_set: list[str],
        artifact_path: str,
        trained_at: str,
        precision_val: Optional[float] = None,
        recall_val: Optional[float] = None,
        f1_val: Optional[float] = None,
        confusion_matrix: Optional[list] = None,
    ) -> None:
        """Atomically deactivate old model and register new active one."""
        with self._connect() as conn:
            conn.execute("UPDATE model_registry SET is_active = 0")
            conn.execute(
                """INSERT OR REPLACE INTO model_registry
                   (model_id, algorithm, dataset, feature_set, precision_val,
                    recall_val, f1_val, confusion_matrix, artifact_path,
                    trained_at, is_active)
                   VALUES (?,?,?,?,?,?,?,?,?,?,1)""",
                (
                    model_id,
                    algorithm,
                    dataset,
                    json.dumps(feature_set),
                    precision_val,
                    recall_val,
                    f1_val,
                    json.dumps(confusion_matrix) if confusion_matrix else None,
                    artifact_path,
                    trained_at,
                ),
            )

    def get_active_model(self) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM model_registry WHERE is_active = 1 LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    # ── Health ─────────────────────────────────────────────────────────────────

    def health_check(self) -> bool:
        try:
            with self._connect() as conn:
                conn.execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False
