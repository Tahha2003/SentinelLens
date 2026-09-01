# SPDX-License-Identifier: MIT
"""
Entity-centric sliding window graph correlator.

Algorithm:
  1. Sort events by timestamp
  2. Group by entity_id (avoids O(n²) global comparison)
  3. For each entity group, add edges between events within the time window
  4. Also link events sharing raw_fields entities (transitive connectivity)
  5. Find connected components → incident clusters
  6. Filter by min_cluster_size, cap at MAX_CLUSTER_SIZE
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import timedelta

import networkx as nx

from sentinellens.models import Event, IncidentCluster, IncidentFeatures
from sentinellens.pipeline.features import FeatureExtractor

logger = logging.getLogger(__name__)

# Fields in raw_fields that may reference related entities
RELATED_ENTITY_FIELDS = ("dest_ip", "src_ip", "dest", "src", "dest_host", "src_host", "user")


class EntityCorrelator:
    MAX_CLUSTER_SIZE = 500       # hard cap — prevents runaway clusters
    HIGH_ACTIVITY_THRESHOLD = 1000  # entity event count above which 5-min window applies

    def __init__(
        self,
        window_minutes: int = 15,
        min_cluster_size: int = 2,
    ) -> None:
        self.window = timedelta(minutes=window_minutes)
        self.strict_window = timedelta(minutes=5)
        self.min_size = min_cluster_size
        self._extractor = FeatureExtractor()

    def correlate(self, events: list[Event], pipeline_run_id: str = "") -> list[IncidentCluster]:
        """
        Correlate a list of normalized Events into IncidentClusters.
        Returns clusters sorted by time_start ascending.
        """
        if not events:
            return []

        # Step 1 — Sort by timestamp
        sorted_events = sorted(events, key=lambda e: e.timestamp)

        # Step 2 — Build graph with one node per event
        G: nx.Graph = nx.Graph()
        G.add_nodes_from(e.event_id for e in sorted_events)

        # Step 3 — Index by entity_id
        by_entity: dict[str, list[Event]] = defaultdict(list)
        for e in sorted_events:
            by_entity[e.entity_id].append(e)

        # Also index events by related entities found in raw_fields
        self._link_related_entities(sorted_events, by_entity, G)

        # Step 4 — Add edges within each entity group
        for entity_id, entity_events in by_entity.items():
            # High-activity guard: use stricter window for busy entities
            w = self.strict_window if len(entity_events) > self.HIGH_ACTIVITY_THRESHOLD else self.window
            if len(entity_events) > self.HIGH_ACTIVITY_THRESHOLD:
                logger.warning(
                    "Entity '%s' has %d events — applying 5-min strict window",
                    entity_id, len(entity_events),
                )

            # Events are sorted → we can break early when window is exceeded
            for i, eA in enumerate(entity_events):
                for eB in entity_events[i + 1:]:
                    delta = eB.timestamp - eA.timestamp
                    if delta <= w:
                        G.add_edge(eA.event_id, eB.event_id)
                    else:
                        break  # sorted — no further matches possible

        # Step 5 — Find connected components
        event_by_id = {e.event_id: e for e in sorted_events}
        clusters: list[IncidentCluster] = []

        for component in nx.connected_components(G):
            if len(component) < self.min_size:
                continue

            cluster_events = [event_by_id[eid] for eid in component]
            cluster_events.sort(key=lambda e: e.timestamp)

            is_truncated = False
            if len(cluster_events) > self.MAX_CLUSTER_SIZE:
                logger.warning(
                    "Cluster truncated from %d to %d events",
                    len(cluster_events), self.MAX_CLUSTER_SIZE,
                )
                cluster_events = cluster_events[:self.MAX_CLUSTER_SIZE]
                is_truncated = True

            cluster = self._build_cluster(cluster_events, pipeline_run_id, is_truncated)
            clusters.append(cluster)

        clusters.sort(key=lambda c: c.time_start)
        logger.info(
            "Correlation: %d events → %d clusters (min_size=%d)",
            len(events), len(clusters), self.min_size,
        )
        return clusters

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _link_related_entities(
        self,
        events: list[Event],
        by_entity: dict[str, list[Event]],
        G: nx.Graph,
    ) -> None:
        """
        For each event, inspect raw_fields for IP/host/user references.
        If those references match another entity group, add the event to that group
        so transitive connections are captured.
        """
        for e in events:
            for field in RELATED_ENTITY_FIELDS:
                val = e.raw_fields.get(field, "")
                if not val or val in ("-", "N/A", ""):
                    continue
                # Try to construct a normalized entity_id
                for prefix in ("ip", "host", "user"):
                    candidate = f"{prefix}:{val}"
                    if candidate != e.entity_id and candidate in by_entity:
                        # Cross-entity edge: connect this event to related entity events
                        for related_event in by_entity[candidate]:
                            delta = abs((e.timestamp - related_event.timestamp).total_seconds())
                            if delta <= self.window.total_seconds():
                                G.add_edge(e.event_id, related_event.event_id)

    def _build_cluster(
        self,
        cluster_events: list[Event],
        pipeline_run_id: str,
        is_truncated: bool,
    ) -> IncidentCluster:
        entities = {e.entity_id for e in cluster_events}
        time_start = cluster_events[0].timestamp
        time_end = cluster_events[-1].timestamp
        features = self._extractor.extract(cluster_events, time_start, time_end)

        # Deterministic cluster_id based on entity + time_start
        # so the same cluster is not re-inserted on every pipeline run
        import hashlib
        id_src = sorted(entities)[0] + time_start.isoformat()
        cluster_id = str(uuid.UUID(hashlib.md5(id_src.encode()).hexdigest()))

        return IncidentCluster(
            cluster_id=cluster_id,
            events=cluster_events,
            entities=entities,
            time_start=time_start,
            time_end=time_end,
            features=features,
            is_truncated=is_truncated,
            pipeline_run_id=pipeline_run_id,
        )
