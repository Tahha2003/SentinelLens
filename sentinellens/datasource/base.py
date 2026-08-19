# SPDX-License-Identifier: MIT
"""
DataSource abstract base class — the critical isolation boundary.

No component downstream of this interface may import
datasource/local.py or datasource/splunk.py directly.
Any violation is an architecture defect.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional


class DataSource(ABC):

    @abstractmethod
    def get_events(
        self,
        query: str,
        start_time: datetime,
        end_time: datetime,
        entity_filter: Optional[list[str]] = None,
    ) -> list[dict]:
        """
        Return a list of raw event dicts within [start_time, end_time].

        The query parameter is a hint (SPL for Splunk, ignored for local).
        entity_filter, if provided, restricts results to those entities.
        Returns raw dicts — normalization happens in the pipeline layer.
        """
        ...

    @abstractmethod
    def get_metrics(
        self,
        host: str,
        metric_type: str,
        timeframe: tuple[datetime, datetime],
    ) -> list[dict]:
        """Return performance metric points for a host. Optional feature."""
        ...

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the data source is reachable and usable."""
        ...

    @abstractmethod
    def source_name(self) -> str:
        """Return 'local_bots' or 'splunk_live'."""
        ...
