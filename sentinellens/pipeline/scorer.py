# SPDX-License-Identifier: MIT
"""
Incident scorer — loads the trained ML model and scores IncidentClusters.

Raises RuntimeError at construction if the model file is missing.
The model file is produced by eval/train.py.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from pathlib import Path

from sentinellens.models import IncidentCluster, ScoredIncident

logger = logging.getLogger(__name__)


class IncidentScorer:
    CONFIDENCE_HIGH = 0.75
    CONFIDENCE_MEDIUM = 0.50

    def __init__(self, model_path: str = "models/scorer_v1.joblib") -> None:
        path = Path(model_path)
        if not path.exists():
            raise RuntimeError(
                f"Scorer model not found at '{path}'. "
                f"Run:  python eval/train.py  to generate it."
            )
        try:
            import joblib
            self._model = joblib.load(path)
        except Exception as exc:
            raise RuntimeError(f"Failed to load scorer model: {exc}") from exc

        self._model_version = self._compute_hash(path)
        logger.info("IncidentScorer loaded model %s (version %s)", path, self._model_version[:12])

    def score(self, cluster: IncidentCluster) -> ScoredIncident:
        """Score a single IncidentCluster and return a ScoredIncident."""
        feature_vec = cluster.features.to_vector()
        prob = float(self._model.predict_proba([feature_vec])[0][1])
        prob = max(0.0, min(1.0, prob))  # clamp to [0, 1]

        return ScoredIncident(
            incident_id=str(uuid.uuid4()),
            cluster=cluster,
            score=prob,
            confidence_band=self._band(prob),
            model_version=self._model_version,
            label=None,
        )

    def score_batch(self, clusters: list[IncidentCluster]) -> list[ScoredIncident]:
        """Score a list of clusters. Returns results sorted by score descending."""
        scored = [self.score(c) for c in clusters]
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _band(self, score: float) -> str:
        if score >= self.CONFIDENCE_HIGH:
            return "HIGH"
        if score >= self.CONFIDENCE_MEDIUM:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _compute_hash(path: Path) -> str:
        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()
