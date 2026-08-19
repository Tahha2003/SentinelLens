# SPDX-License-Identifier: MIT
"""
Feature extractor — computes the 9-feature vector for each IncidentCluster.

The ORDER of features in IncidentFeatures.to_vector() is a frozen contract.
Never reorder without retraining the model.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime
from typing import Optional

from sentinellens.models import Event, IncidentFeatures


class FeatureExtractor:

    def extract(
        self,
        events: list[Event],
        time_start: datetime,
        time_end: datetime,
        metric_points: Optional[list] = None,
    ) -> IncidentFeatures:
        """
        Compute all 9 features from a list of correlated events.
        metric_points is optional (Phase 1 performance-deviation feature).
        """
        n = len(events)

        # 1. event_count
        event_count = n

        # 2. event_type_entropy — Shannon entropy of event_type distribution
        type_counts = Counter(e.event_type for e in events)
        event_type_entropy = self._entropy(list(type_counts.values()))

        # 3. severity_sum
        severity_sum = sum(e.severity for e in events)

        # 4. severity_max
        severity_max = max(e.severity for e in events)

        # 5. entity_fan_out — count of distinct entity_ids
        entity_fan_out = len({e.entity_id for e in events})

        # 6 & 7. time_density and time_span_minutes
        delta_secs = (time_end - time_start).total_seconds()
        time_span_minutes = delta_secs / 60.0
        # Avoid division by zero for single-second clusters
        time_density = event_count / max(time_span_minutes, 0.1)

        # 8. unique_sources — count of distinct event.source values
        unique_sources = len({e.source for e in events})

        # 9. perf_deviation_max — optional
        perf_deviation_max: Optional[float] = None
        if metric_points:
            zscores = [
                mp.zscore for mp in metric_points if mp.zscore is not None
            ]
            if zscores:
                perf_deviation_max = max(zscores)

        return IncidentFeatures(
            event_count=event_count,
            event_type_entropy=event_type_entropy,
            severity_sum=severity_sum,
            severity_max=severity_max,
            entity_fan_out=entity_fan_out,
            time_density=time_density,
            time_span_minutes=time_span_minutes,
            unique_sources=unique_sources,
            perf_deviation_max=perf_deviation_max,
        )

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _entropy(counts: list[int]) -> float:
        """Shannon entropy (base 2) from a list of counts."""
        total = sum(counts)
        if total == 0:
            return 0.0
        probs = [c / total for c in counts if c > 0]
        return -sum(p * math.log2(p) for p in probs)
