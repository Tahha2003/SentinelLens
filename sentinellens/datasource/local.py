# SPDX-License-Identifier: MIT
"""
LocalFileDataSource — reads pre-exported BOTS JSON/CSV files.

Thread-safe: data is read-only after __init__.
The query parameter is ignored (local files have no query engine).
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sentinellens.datasource.base import DataSource

logger = logging.getLogger(__name__)


def _parse_ts(raw: dict) -> Optional[datetime]:
    """Try to parse _time from a raw BOTS event dict. Returns None on failure."""
    val = raw.get("_time") or raw.get("timestamp") or raw.get("time")
    if val is None:
        return None
    # Epoch float (BOTS standard)
    try:
        return datetime.fromtimestamp(float(val), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        pass
    # ISO8601 string
    try:
        ts = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    except ValueError:
        return None


class LocalFileDataSource(DataSource):

    def __init__(self, data_path: str) -> None:
        path = Path(data_path)
        if not path.exists():
            raise FileNotFoundError(
                f"BOTS data file not found: {path}. "
                f"Set BOTS_DATA_PATH in .env or provide the file."
            )
        self._raw_events: list[dict] = self._load(path)
        logger.info("LocalFileDataSource loaded %d events from %s", len(self._raw_events), path)

    # ── Loading ────────────────────────────────────────────────────────────────

    def _load(self, path: Path) -> list[dict]:
        suffix = path.suffix.lower()
        if suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            # Support both top-level array and {"results": [...]} wrapper
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                for key in ("results", "events", "data"):
                    if key in data and isinstance(data[key], list):
                        return data[key]
            return []
        if suffix == ".csv":
            with open(path, newline="", encoding="utf-8") as f:
                return list(csv.DictReader(f))
        raise ValueError(f"Unsupported data format: {suffix}. Use .json or .csv")

    # ── DataSource interface ───────────────────────────────────────────────────

    def get_events(
        self,
        query: str = "",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        entity_filter: Optional[list[str]] = None,
    ) -> list[dict]:
        results = self._raw_events

        # Time window filtering
        if start_time or end_time:
            filtered = []
            for raw in results:
                ts = _parse_ts(raw)
                if ts is None:
                    filtered.append(raw)  # pass through if unparseable — normalizer handles reject
                    continue
                if start_time and ts < start_time:
                    continue
                if end_time and ts > end_time:
                    continue
                filtered.append(raw)
            results = filtered

        # Entity filter (best-effort on raw fields)
        if entity_filter:
            entity_set = set(entity_filter)
            results = [
                r for r in results
                if (
                    r.get("src_ip") in entity_set
                    or r.get("dest_ip") in entity_set
                    or r.get("user") in entity_set
                    or r.get("host") in entity_set
                    or r.get("entity_id") in entity_set
                )
            ]

        return results

    def get_metrics(
        self,
        host: str,
        metric_type: str,
        timeframe: tuple[datetime, datetime],
    ) -> list[dict]:
        # Performance metrics not available in static BOTS export
        return []

    def health_check(self) -> bool:
        return len(self._raw_events) > 0

    def source_name(self) -> str:
        return "local_bots"
