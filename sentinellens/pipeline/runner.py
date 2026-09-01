# SPDX-License-Identifier: MIT
"""
PipelineRunner — orchestrates the full Phase 0 pipeline.

Flow:
  DataSource → Normalizer → Correlator → FeatureExtractor → Scorer → Repository
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from sentinellens import config
from sentinellens.datasource.factory import get_datasource
from sentinellens.db.repository import Repository
from sentinellens.pipeline.correlator import EntityCorrelator
from sentinellens.pipeline.normalizer import EventNormalizer
from sentinellens.pipeline.scorer import IncidentScorer

logger = logging.getLogger(__name__)

# Global scorer instance — loaded once at startup
_scorer: Optional[IncidentScorer] = None
_scorer_lock = threading.Lock()


def get_scorer() -> IncidentScorer:
    global _scorer
    if _scorer is None:
        with _scorer_lock:
            if _scorer is None:
                _scorer = IncidentScorer(config.MODEL_PATH)
    return _scorer


class PipelineRunner:

    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    def run_async(self) -> str:
        """
        Start a pipeline run in a background thread.
        Returns run_id immediately — caller polls /pipeline/status/{run_id}.
        """
        run_id = str(uuid.uuid4())
        datasource = get_datasource()
        self._repo.save_pipeline_run(run_id, datasource.source_name())
        self._repo.update_pipeline_run(run_id, status="queued")

        thread = threading.Thread(
            target=self._execute,
            args=(run_id,),
            daemon=True,
            name=f"pipeline-{run_id[:8]}",
        )
        thread.start()
        logger.info("Pipeline run %s started (thread %s)", run_id[:8], thread.name)
        return run_id

    def run_sync(self) -> str:
        """
        Run pipeline synchronously. Used by make demo and eval scripts.
        Returns run_id after completion.
        """
        run_id = str(uuid.uuid4())
        datasource = get_datasource()
        self._repo.save_pipeline_run(run_id, datasource.source_name())
        self._execute(run_id)
        return run_id

    # ── Internal execution ─────────────────────────────────────────────────────

    def _execute(self, run_id: str) -> None:
        self._repo.update_pipeline_run(run_id, status="running")

        try:
            # ── Step 1: Fetch raw events ───────────────────────────────────────
            datasource = get_datasource()
            raw_events = datasource.get_events("", None, None)
            event_count = len(raw_events)
            logger.info("[%s] Fetched %d raw events", run_id[:8], event_count)

            # ── Step 2: Normalize ──────────────────────────────────────────────
            normalizer = EventNormalizer(datasource.source_name())
            events, failures = normalizer.normalize_batch(raw_events)
            normalized_count = len(events)
            logger.info(
                "[%s] Normalized: %d ok, %d failures",
                run_id[:8], normalized_count, failures,
            )

            # ── Step 3: Persist events ─────────────────────────────────────────
            self._repo.insert_events(events)

            # ── Step 4: Correlate ──────────────────────────────────────────────
            correlator = EntityCorrelator(
                window_minutes=config.CORRELATION_WINDOW_MINUTES,
                min_cluster_size=config.MIN_CLUSTER_SIZE,
            )
            clusters = correlator.correlate(events, pipeline_run_id=run_id)
            cluster_count = len(clusters)
            logger.info("[%s] Correlation: %d clusters", run_id[:8], cluster_count)

            # ── Step 5: Score ──────────────────────────────────────────────────
            scorer = get_scorer()
            scored_incidents = scorer.score_batch(clusters)

            # ── Step 6: Persist clusters + scores ─────────────────────────────
            for cluster in clusters:
                self._repo.insert_cluster(cluster)

            for si in scored_incidents:
                self._repo.insert_scored_incident(si)

            # ── Step 7: Mark complete ──────────────────────────────────────────
            self._repo.update_pipeline_run(
                run_id,
                status="complete",
                event_count=event_count,
                normalized_count=normalized_count,
                cluster_count=cluster_count,
                normalization_failures=failures,
                completed_at=datetime.now(tz=timezone.utc).isoformat(),
            )
            logger.info(
                "[%s] Pipeline complete — %d incidents scored",
                run_id[:8], len(scored_incidents),
            )

        except Exception as exc:
            logger.exception("[%s] Pipeline FAILED: %s", run_id[:8], exc)
            self._repo.update_pipeline_run(
                run_id,
                status="failed",
                error_message=str(exc),
                completed_at=datetime.now(tz=timezone.utc).isoformat(),
            )
