# SPDX-License-Identifier: MIT
"""
SplunkDataSource — Phase 1 implementation.

Uses Splunk REST API directly (HTTPS + Bearer token) to avoid SDK parser
issues with BOTS v3 data that contains binary/special-character fields.
"""

from __future__ import annotations

import json
import logging
import ssl
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from sentinellens.datasource.base import DataSource

logger = logging.getLogger(__name__)

# Shared SSL context — self-signed cert on local Splunk is fine for demo
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


class SplunkDataSource(DataSource):
    HEALTH_CHECK_TIMEOUT_SECS = 5
    HEALTH_CHECK_RETRIES = 2
    BASE_INDEX = "botsv3"

    def __init__(self, host: str, port: int, token: str) -> None:
        self._base_url = f"https://{host}:{port}"
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        logger.info("SplunkDataSource initialized (%s:%d)", host, port)

    # ── DataSource interface ───────────────────────────────────────────────────

    def get_events(
        self,
        query: str = "",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        entity_filter: Optional[list[str]] = None,
    ) -> list[dict]:
        try:
            spl = query or self._build_spl(start_time, end_time)
            results = self._oneshot(spl, count=5000)
            logger.info("Splunk returned %d events", len(results))
            return results
        except Exception as exc:
            logger.error("Splunk get_events failed: %s", exc)
            return []

    def get_metrics(
        self,
        host: str,
        metric_type: str,
        timeframe: tuple[datetime, datetime],
    ) -> list[dict]:
        # Optional Phase 1 feature — stub
        return []

    def health_check(self) -> bool:
        for attempt in range(self.HEALTH_CHECK_RETRIES):
            try:
                req = urllib.request.Request(
                    f"{self._base_url}/services/server/info?output_mode=json",
                    headers=self._headers,
                )
                with urllib.request.urlopen(
                    req, context=_SSL_CTX,
                    timeout=self.HEALTH_CHECK_TIMEOUT_SECS
                ) as resp:
                    data = json.loads(resp.read())
                    return bool(data.get("entry"))
            except Exception:
                if attempt < self.HEALTH_CHECK_RETRIES - 1:
                    time.sleep(0.5)
        return False

    def source_name(self) -> str:
        return "splunk_live"

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _build_spl(
        self,
        start_time: Optional[datetime],
        end_time: Optional[datetime],
    ) -> str:
        if start_time is None and end_time is None:
            # BOTS v3 is a static 2018 dataset — always fetch with earliest=0
            return (
                f"search index={self.BASE_INDEX} earliest=0 "
                f"| fields _time,sourcetype,host,src_ip,dest_ip,user,"
                f"source,severity,urgency,EventCode,action,bytes_in,bytes_out"
            )
        earliest = _iso(start_time) if start_time else "0"
        latest = _iso(end_time) if end_time else "now"
        return (
            f'search index={self.BASE_INDEX} earliest="{earliest}" latest="{latest}" '
            f"| fields _time,sourcetype,host,src_ip,dest_ip,user,"
            f"source,severity,urgency,EventCode,action,bytes_in,bytes_out"
        )

    def _oneshot(self, spl: str, count: int = 5000) -> list[dict]:
        """
        Execute a oneshot Splunk search via REST API.
        Returns a list of result dicts.
        """
        data = urllib.parse.urlencode({
            "search": spl,
            "output_mode": "json",
            "count": str(count),
            "exec_mode": "oneshot",
        }).encode()

        req = urllib.request.Request(
            f"{self._base_url}/services/search/jobs",
            data=data,
            headers=self._headers,
        )
        with urllib.request.urlopen(req, context=_SSL_CTX, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))

        return body.get("results", [])
