# SPDX-License-Identifier: MIT
"""
SentinelLens data contracts.

These dataclasses are the internal type system. Every module receives and
returns these types — never raw dicts except at the datasource boundary.
Field order in IncidentFeatures.to_vector() is a FROZEN contract —
changing it without retraining the model produces silently wrong scores.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# ── Enums ──────────────────────────────────────────────────────────────────────

class EntityType(str, Enum):
    USER = "USER"
    HOST = "HOST"
    IP = "IP"
    PROCESS = "PROCESS"
    URL = "URL"
    UNKNOWN = "UNKNOWN"


class ConfidenceBand(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# ── Core Event ─────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Event:
    """
    Canonical internal representation of a normalized security event.

    Immutable after construction. raw_fields preserves the original record
    verbatim and is never mutated.
    """

    event_id: str                   # UUID4 string, generated at normalization
    timestamp: datetime             # UTC, tzinfo must be set — never naive
    entity_id: str                  # Prefix-normalized: 'user:alice', 'host:dc01', 'ip:10.0.0.1'
    entity_type: EntityType
    event_type: str                 # CIM-normalized string, 'unknown' if unmapped
    severity: int                   # 1-5
    source: str                     # '{datasource}:{sourcetype}'
    raw_fields: dict                # Original record — immutable after construction
    tags: tuple = field(default_factory=tuple)  # tuple not list — frozen dataclass requirement

    def __post_init__(self) -> None:
        if not (1 <= self.severity <= 5):
            raise ValueError(f"severity must be 1–5, got {self.severity}")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware (UTC)")

    def to_db_row(self) -> tuple:
        """Return a tuple suitable for parameterized SQLite insert."""
        return (
            self.event_id,
            self.timestamp.isoformat(),
            self.entity_id,
            self.entity_type.value,
            self.event_type,
            self.severity,
            self.source,
            json.dumps(self.raw_fields),
            json.dumps(list(self.tags)),
        )


# ── Metric Point (optional perf-deviation feature) ────────────────────────────

@dataclass(frozen=True)
class MetricPoint:
    host: str
    metric_type: str        # 'cpu_pct' | 'mem_pct' | 'net_bytes_out'
    value: float
    timestamp: datetime
    baseline: Optional[float] = None   # Rolling 24h mean; None if < 24h history

    @property
    def zscore(self) -> Optional[float]:
        """Z-score relative to baseline. None if no baseline."""
        if self.baseline is None:
            return None
        std = self.baseline * 0.15  # conservative 15% std-dev estimate
        if std <= 0:
            return 0.0
        return (self.value - self.baseline) / std


# ── Incident Features ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class IncidentFeatures:
    """
    9-feature vector extracted from an IncidentCluster.

    The order of fields in to_vector() is a frozen contract —
    the ML model is trained on this exact order.
    """

    event_count: int            # len(cluster.events)
    event_type_entropy: float   # Shannon entropy of event_type distribution
    severity_sum: int           # sum of all event.severity values
    severity_max: int           # maximum severity in cluster
    entity_fan_out: int         # count of distinct entity_ids
    time_density: float         # events_per_minute over cluster duration
    time_span_minutes: float    # (time_end - time_start).total_seconds() / 60
    unique_sources: int         # count of distinct event.source values
    perf_deviation_max: Optional[float] = None   # max z-score; None if no metrics

    def to_vector(self) -> list[float]:
        """Ordered feature vector for the ML model. Order MUST match training."""
        return [
            float(self.event_count),
            float(self.event_type_entropy),
            float(self.severity_sum),
            float(self.severity_max),
            float(self.entity_fan_out),
            float(self.time_density),
            float(self.time_span_minutes),
            float(self.unique_sources),
            float(self.perf_deviation_max) if self.perf_deviation_max is not None else 0.0,
        ]

    def to_dict(self) -> dict:
        return {
            "event_count": self.event_count,
            "event_type_entropy": round(self.event_type_entropy, 4),
            "severity_sum": self.severity_sum,
            "severity_max": self.severity_max,
            "entity_fan_out": self.entity_fan_out,
            "time_density": round(self.time_density, 4),
            "time_span_minutes": round(self.time_span_minutes, 2),
            "unique_sources": self.unique_sources,
            "perf_deviation_max": self.perf_deviation_max,
        }


# ── Incident Cluster ───────────────────────────────────────────────────────────

@dataclass
class IncidentCluster:
    """
    A group of correlated security events forming a potential incident.

    NOT frozen — the correlator builds this incrementally.
    """

    cluster_id: str
    events: list[Event]
    entities: set           # set[str] — all distinct entity_ids
    time_start: datetime
    time_end: datetime
    features: IncidentFeatures
    is_truncated: bool = False      # True if cluster hit MAX_CLUSTER_SIZE cap
    pipeline_run_id: str = ""

    @property
    def duration_minutes(self) -> float:
        delta = self.time_end - self.time_start
        return delta.total_seconds() / 60.0

    @property
    def top_entities(self) -> list[str]:
        """Return up to 5 most-referenced entities."""
        from collections import Counter
        counts = Counter(e.entity_id for e in self.events)
        return [eid for eid, _ in counts.most_common(5)]


# ── Scored Incident ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ScoredIncident:
    incident_id: str
    cluster: IncidentCluster
    score: float                    # 0.0–1.0 probability from model.predict_proba()
    confidence_band: str            # 'HIGH' | 'MEDIUM' | 'LOW'
    model_version: str              # SHA256 of scorer .joblib artifact
    label: Optional[int] = None    # Ground truth (eval only). None in production.

    def to_api_dict(self) -> dict:
        """Serialize for the REST API incidents list endpoint."""
        return {
            "incident_id": self.incident_id,
            "score": round(self.score, 4),
            "confidence_band": self.confidence_band,
            "event_count": self.cluster.features.event_count,
            "entity_count": len(self.cluster.entities),
            "time_start": self.cluster.time_start.isoformat(),
            "time_end": self.cluster.time_end.isoformat(),
            "duration_minutes": round(self.cluster.duration_minutes, 1),
            "top_entities": self.cluster.top_entities,
            "severity_max": self.cluster.features.severity_max,
            "is_truncated": self.cluster.is_truncated,
            "model_version": self.model_version,
        }


# ── Investigation Result (Phase 2) ────────────────────────────────────────────

@dataclass(frozen=True)
class InvestigationResult:
    analyst_query: str
    spl_generated: Optional[str]       # SPL produced; None if agent failed
    result_raw: Optional[list[dict]]   # Raw Splunk results; None if no results
    result_summary: str                # Always populated, even if 'No results found'
    agent_backend: str                 # 'mcp_server' | 'splunk_sdk' | 'local_mock'


# ── Helper ─────────────────────────────────────────────────────────────────────

def sha8(value: str) -> str:
    """Return first 8 hex chars of SHA-256 — used for unknown entity fallback IDs."""
    return hashlib.sha256(value.encode()).hexdigest()[:8]
