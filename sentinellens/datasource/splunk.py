# SPDX-License-Identifier: MIT
"""
SplunkDataSource — Phase 1 implementation.

Connects to a live Splunk instance via the Splunk Python SDK.
Falls back gracefully if the SDK is not installed or connection fails.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from sentinellens.datasource.base import DataSource

logger = logging.getLogger(__name__)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


class SplunkDataSource(DataSource):
    HEALTH_CHECK_TIMEOUT_SECS = 5
    HEALTH_CHECK_RETRIES = 2

    def __init__(self, host: str, port: int, token: str) -> None:
        try:
            import splunklib.client as client  # type: ignore
            self._service = client.connect(
                host=host,
                port=port,
                splunkToken=token,
            )
            logger.info("SplunkDataSource connected to %s:%d", host, port)
        except ImportError:
            raise RuntimeError(
                "splunk-sdk is not installed. "
                "Add it to requirements.txt for Phase 1."
            )

    def get_events(
        self,
        query: str = "",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        entity_filter: Optional[list[str]] = None,
    ) -> list[dict]:
        try:
            from splunklib.results import ResultsReader  # type: ignore

            spl = query or self._build_spl(start_time, end_time)
            results = self._service.jobs.oneshot(spl, count=10000)
            return [dict(r) for r in ResultsReader(results)]
        except Exception as exc:
            logger.error("Splunk query failed: %s", exc)
            return []

    def _build_spl(
        self,
        start_time: Optional[datetime],
        end_time: Optional[datetime],
    ) -> str:
        earliest = _iso(start_time) if start_time else "-24h"
        latest = _iso(end_time) if end_time else "now"
        return f'search index=* earliest="{earliest}" latest="{latest}" | head 10000'

    def get_metrics(
        self,
        host: str,
        metric_type: str,
        timeframe: tuple[datetime, datetime],
    ) -> list[dict]:
        # Optional Phase 1 feature — stub for now
        return []

    def health_check(self) -> bool:
        for attempt in range(self.HEALTH_CHECK_RETRIES):
            try:
                self._service.info()
                return True
            except Exception:
                if attempt < self.HEALTH_CHECK_RETRIES - 1:
                    time.sleep(0.5)
        return False

    def source_name(self) -> str:
        return "splunk_live"
