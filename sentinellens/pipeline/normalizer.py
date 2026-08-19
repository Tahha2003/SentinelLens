# SPDX-License-Identifier: MIT
"""
Event normalizer — converts raw BOTS/Splunk dicts to the canonical Event schema.

Every normalization error is logged with the raw record and counted.
Silent failures corrupt clustering — this module treats errors as first-class events.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sentinellens.models import EntityType, Event, sha8

logger = logging.getLogger(__name__)

# ── CIM event-type mapping ─────────────────────────────────────────────────────
# Maps Splunk sourcetype → normalized CIM event_type string
SOURCETYPE_MAP: dict[str, str] = {
    # Authentication
    "wineventlog":                          "authentication",
    "xmlwineventlog:microsoft-windows-sysmon/operational": "endpoint",
    "linux_secure":                         "authentication",
    "linux_audit":                          "authentication",
    # Network
    "stream:http":                          "network_traffic",
    "stream:tcp":                           "network_traffic",
    "stream:udp":                           "network_traffic",
    "stream:dns":                           "dns",
    "stream:smtp":                          "email",
    "stream:smb":                           "network_traffic",
    "aws:cloudwatchlogs:vpcflow":           "network_traffic",
    "cisco:asa":                            "network_traffic",
    # Endpoint / Malware
    "xmlwineventlog":                       "endpoint",
    "symantec:ep:risk:file":                "malware",
    "symantec:ep:behavior:file":            "endpoint",
    "symantec:ep:security:file":            "intrusion_detection",
    "symantec:ep:traffic:file":             "network_traffic",
    # Cloud
    "aws:cloudtrail":                       "cloud_audit",
    "aws:cloudwatch:guardduty":             "intrusion_detection",
    "ms:aad:signin":                        "authentication",
    "ms:o365:management":                   "cloud_audit",
    "o365:management:activity":             "cloud_audit",
    # Generic
    "syslog":                               "system",
    "perfmonmk:process":                    "performance",
    # Synthetic / test
    "bots:synthetic":                       "synthetic",
}

# ── Severity mapping ───────────────────────────────────────────────────────────
SEVERITY_MAP: dict[str, int] = {
    "informational": 1, "info": 1, "1": 1,
    "low": 2, "2": 2,
    "medium": 3, "med": 3, "3": 3,
    "high": 4, "4": 4,
    "critical": 5, "crit": 5, "5": 5,
    # Splunk urgency field
    "unknown": 2,
}


class EventNormalizer:

    def __init__(self, datasource_name: str = "local_bots") -> None:
        self._source_prefix = datasource_name
        self._failures = 0

    @property
    def failure_count(self) -> int:
        return self._failures

    def reset_counters(self) -> None:
        self._failures = 0

    # ── Public API ─────────────────────────────────────────────────────────────

    def normalize(self, raw: dict) -> Optional[Event]:
        """
        Normalize a single raw event dict to an Event.
        Returns None and increments failure counter if timestamp is missing.
        """
        try:
            ts = self._parse_timestamp(raw)
            if ts is None:
                self._log_failure("missing_timestamp", raw)
                return None

            entity_id = self._extract_entity(raw)
            entity_type = self._infer_entity_type(entity_id)
            event_type = self._map_event_type(raw)
            severity = self._parse_severity(raw)
            source = self._build_source(raw)

            return Event(
                event_id=str(uuid.uuid4()),
                timestamp=ts,
                entity_id=entity_id,
                entity_type=entity_type,
                event_type=event_type,
                severity=severity,
                source=source,
                raw_fields=raw,
                tags=tuple(raw.get("tags", [])) if isinstance(raw.get("tags"), list) else (),
            )
        except Exception as exc:
            self._log_failure(str(exc), raw)
            return None

    def normalize_batch(self, raws: list[dict]) -> tuple[list[Event], int]:
        """
        Normalize a list of raw events.
        Returns (events, failure_count).
        """
        events: list[Event] = []
        batch_failures = 0
        for raw in raws:
            result = self.normalize(raw)
            if result:
                events.append(result)
            else:
                batch_failures += 1
        return events, batch_failures

    # ── Field parsers ──────────────────────────────────────────────────────────

    def _parse_timestamp(self, raw: dict) -> Optional[datetime]:
        for key in ("_time", "timestamp", "time", "EventTime"):
            val = raw.get(key)
            if val is None:
                continue
            # Epoch float
            try:
                return datetime.fromtimestamp(float(val), tz=timezone.utc)
            except (TypeError, ValueError, OSError):
                pass
            # ISO8601 string
            try:
                s = str(val).replace("Z", "+00:00")
                dt = datetime.fromisoformat(s)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                pass
        return None

    def _extract_entity(self, raw: dict) -> str:
        """
        Return a prefix-normalized entity_id: 'user:alice', 'host:dc01', 'ip:10.0.0.1'.
        Falls back to 'unknown:<sha8(repr)>' if nothing usable is found.
        """
        # Pre-normalized (synthetic data or already processed)
        if "entity_id" in raw:
            return str(raw["entity_id"])

        # User
        for key in ("user", "User", "account_name", "AccountName", "src_user"):
            v = raw.get(key, "")
            if v and v not in ("-", "N/A", ""):
                return f"user:{v.lower()}"

        # Host
        for key in ("host", "Host", "ComputerName", "dest_host", "src_host"):
            v = raw.get(key, "")
            if v and v not in ("-", "N/A", "", "localhost"):
                return f"host:{v.lower()}"

        # IP address (src preferred over dest for entity grouping)
        for key in ("src_ip", "src", "source_ip", "dest_ip", "dest", "destination_ip"):
            v = raw.get(key, "")
            if v and v not in ("-", "N/A", "", "0.0.0.0"):
                return f"ip:{v}"

        # Fallback — deterministic unknown ID
        return f"unknown:{sha8(repr(raw))}"

    def _infer_entity_type(self, entity_id: str) -> EntityType:
        prefix = entity_id.split(":")[0].upper()
        return EntityType.__members__.get(prefix, EntityType.UNKNOWN)

    def _map_event_type(self, raw: dict) -> str:
        sourcetype = (
            raw.get("sourcetype")
            or raw.get("source_type")
            or raw.get("event_type")
            or ""
        ).lower()
        return SOURCETYPE_MAP.get(sourcetype, "unknown")

    def _parse_severity(self, raw: dict) -> int:
        for key in ("severity", "urgency", "risk_score", "Severity", "priority"):
            val = raw.get(key)
            if val is None:
                continue
            s = str(val).lower().strip()
            if s in SEVERITY_MAP:
                return SEVERITY_MAP[s]
            # Numeric strings
            try:
                n = int(float(s))
                if 1 <= n <= 5:
                    return n
                if n >= 80:
                    return 5
                if n >= 60:
                    return 4
                if n >= 40:
                    return 3
                if n >= 20:
                    return 2
                return 1
            except ValueError:
                pass
        return 2  # default: LOW

    def _build_source(self, raw: dict) -> str:
        sourcetype = raw.get("sourcetype") or raw.get("source_type") or "unknown"
        return f"{self._source_prefix}:{sourcetype}"

    # ── Logging ────────────────────────────────────────────────────────────────

    def _log_failure(self, reason: str, raw: dict) -> None:
        self._failures += 1
        # Log only first 10 failures in detail to avoid log spam on bad datasets
        if self._failures <= 10:
            logger.warning(
                "Normalization failure #%d (%s): %s",
                self._failures, reason,
                {k: v for k, v in list(raw.items())[:5]},
            )
        elif self._failures == 11:
            logger.warning("Further normalization failures will be counted but not logged individually.")
