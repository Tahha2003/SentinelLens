# SPDX-License-Identifier: MIT
"""
SentinelLens ML training script.

Trains LogisticRegression and GradientBoostingClassifier on the BOTS sample data.
Selects the model with higher F1 on held-out set, serializes it to models/scorer_v1.joblib,
and writes a human-readable evaluation report to eval/scorer_report.md.

Usage:
    python eval/train.py

Reproducibility:
    RANDOM_SEED = 42  — never change without bumping version
    TEST_SPLIT   = 0.2
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make sure project root is in path when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from sentinellens.datasource.local import LocalFileDataSource
from sentinellens.pipeline.correlator import EntityCorrelator
from sentinellens.pipeline.features import FeatureExtractor
from sentinellens.pipeline.normalizer import EventNormalizer

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
RANDOM_SEED = 42       # NEVER change without version bump — breaks reproducibility
TEST_SPLIT   = 0.2
DATA_PATH    = os.getenv("BOTS_DATA_PATH", "data/bots_sample_events.json")
MODEL_PATH   = Path(os.getenv("MODEL_PATH", "models/scorer_v1.joblib"))
REPORT_PATH  = Path("eval/scorer_report.md")
FEATURE_NAMES = [
    "event_count",
    "event_type_entropy",
    "severity_sum",
    "severity_max",
    "entity_fan_out",
    "time_density",
    "time_span_minutes",
    "unique_sources",
    "perf_deviation_max",
]


def build_labeled_dataset() -> tuple[list[list[float]], list[int]]:
    """
    Run the full pipeline on the BOTS sample data and extract
    (feature_vectors, labels) for ML training.

    Labels come from the 'label' field in the raw events —
    a cluster is labeled 1 if ANY of its events has label=1.
    """
    logger.info("Loading data from %s", DATA_PATH)
    ds = LocalFileDataSource(DATA_PATH)
    raw_events = ds.get_events("", None, None)

    logger.info("Normalizing %d raw events...", len(raw_events))
    normalizer = EventNormalizer("local_bots")
    events, failures = normalizer.normalize_batch(raw_events)
    logger.info("Normalized: %d events, %d failures", len(events), failures)

    # Preserve label mapping from raw events (event_id → label)
    label_map: dict[str, int] = {}
    for i, raw in enumerate(raw_events):
        lbl = raw.get("label")
        if lbl is not None and i < len(events):
            label_map[events[i].event_id] = int(lbl)

    logger.info("Correlating events into clusters...")
    correlator = EntityCorrelator(window_minutes=15, min_cluster_size=2)
    clusters = correlator.correlate(events)
    logger.info("Produced %d clusters", len(clusters))

    if not clusters:
        raise RuntimeError(
            "No clusters produced from the data. "
            "Check that the sample data has related events within the time window."
        )

    X: list[list[float]] = []
    y: list[int] = []

    for cluster in clusters:
        vec = cluster.features.to_vector()
        # Label cluster 1 if ANY member event is labeled incident
        cluster_label = max(
            (label_map.get(e.event_id, 0) for e in cluster.events),
            default=0,
        )
        X.append(vec)
        y.append(cluster_label)

    n_incidents = sum(y)
    logger.info(
        "Dataset: %d clusters total — %d incidents (label=1), %d noise (label=0)",
        len(y), n_incidents, len(y) - n_incidents,
    )
    return X, y


def train_and_evaluate() -> None:
    X, y = build_labeled_dataset()

    if len(set(y)) < 2:
        logger.warning("Only one class in dataset — skipping training, writing dummy model")
        _write_dummy_model()
        return

    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=TEST_SPLIT,
        random_state=RANDOM_SEED,
        stratify=y,
    )
    logger.info(
        "Train/test split: %d train, %d test (seed=%d, stratified)",
        len(X_train), len(X_test), RANDOM_SEED,
    )

    candidates = {
        "logistic_regression": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", LogisticRegression(max_iter=1000, random_state=RANDOM_SEED)),
        ]),
        "gradient_boosting": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", GradientBoostingClassifier(random_state=RANDOM_SEED)),
        ]),
    }

    results: dict[str, dict] = {}
    for name, pipeline in candidates.items():
        pipeline.fit(X_train, y_train)
        y_pred = pipeline.predict(X_test)
        f1   = f1_score(y_test, y_pred, zero_division=0)
        prec = precision_score(y_test, y_pred, zero_division=0)
        rec  = recall_score(y_test, y_pred, zero_division=0)
        cm   = confusion_matrix(y_test, y_pred).tolist()
        report = classification_report(y_test, y_pred, zero_division=0)
        results[name] = {
            "pipeline": pipeline,
            "f1": f1,
            "precision": prec,
            "recall": rec,
            "confusion_matrix": cm,
            "report": report,
        }
        logger.info("%s — precision=%.3f  recall=%.3f  F1=%.3f", name, prec, rec, f1)

    # Select model with higher F1
    best_name = max(results, key=lambda n: results[n]["f1"])
    best      = results[best_name]
    logger.info("Selected: %s (F1=%.3f)", best_name, best["f1"])

    # Serialize winning model
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(best["pipeline"], MODEL_PATH)
    logger.info("Model saved to %s", MODEL_PATH)

    model_hash = hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()
    trained_at = datetime.now(tz=timezone.utc).isoformat()

    # Register in DB if it exists
    try:
        from sentinellens.db.repository import Repository
        repo = Repository()
        repo.register_model(
            model_id=model_hash,
            algorithm=best_name,
            dataset="bots_v3_synthetic_seed42",
            feature_set=FEATURE_NAMES,
            artifact_path=str(MODEL_PATH),
            trained_at=trained_at,
            precision_val=best["precision"],
            recall_val=best["recall"],
            f1_val=best["f1"],
            confusion_matrix=best["confusion_matrix"],
        )
        logger.info("Model registered in DB (model_id=%s...)", model_hash[:12])
    except Exception as exc:
        logger.warning("Could not register model in DB: %s", exc)

    # Write evaluation report
    _write_report(best_name, best, model_hash, trained_at, results)


def _write_report(
    best_name: str,
    best: dict,
    model_hash: str,
    trained_at: str,
    all_results: dict,
) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    other_name = [n for n in all_results if n != best_name][0]
    other = all_results[other_name]

    lines = [
        "# SentinelLens Scorer Evaluation Report",
        "",
        f"**Generated:** {trained_at}",
        f"**Random seed:** {RANDOM_SEED}",
        f"**Test split:** {TEST_SPLIT} (stratified)",
        f"**Dataset:** {DATA_PATH}",
        "",
        "---",
        "",
        "## Selected Model",
        "",
        f"**Algorithm:** `{best_name}`",
        f"**Model hash (SHA256):** `{model_hash}`",
        f"**Artifact:** `{MODEL_PATH}`",
        "",
        f"| Metric    | Value  |",
        f"|-----------|--------|",
        f"| Precision | {best['precision']:.4f} |",
        f"| Recall    | {best['recall']:.4f} |",
        f"| F1        | {best['f1']:.4f} |",
        "",
        "### Classification Report",
        "",
        "```",
        best["report"],
        "```",
        "",
        "### Confusion Matrix",
        "",
        "```",
        f"              Predicted",
        f"              Noise  Incident",
        f"Actual Noise    {best['confusion_matrix'][0][0]}       {best['confusion_matrix'][0][1]}",
        f"       Incident {best['confusion_matrix'][1][0]}       {best['confusion_matrix'][1][1]}",
        "```",
        "",
        "---",
        "",
        "## Comparison: Both Algorithms",
        "",
        f"| Algorithm             | Precision | Recall | F1     |",
        f"|-----------------------|-----------|--------|--------|",
        f"| {best_name:<21} | {best['precision']:.4f}    | {best['recall']:.4f} | {best['f1']:.4f} | ← SELECTED |",
        f"| {other_name:<21} | {other['precision']:.4f}    | {other['recall']:.4f} | {other['f1']:.4f} |",
        "",
        "---",
        "",
        "## Feature Vector (frozen order)",
        "",
        "| # | Feature              |",
        "|---|----------------------|",
    ]
    for i, feat in enumerate(FEATURE_NAMES):
        lines.append(f"| {i} | `{feat}` |")

    lines += [
        "",
        "---",
        "",
        "> **Note:** All metrics are computed on the held-out test split.",
        "> No metric in this report was hand-written or estimated.",
        "> Reproduce by running: `python eval/train.py`",
    ]

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Evaluation report written to %s", REPORT_PATH)


def _write_dummy_model() -> None:
    """Fallback: write a trivial always-predict-1 model when only one class exists."""
    from sklearn.dummy import DummyClassifier
    dummy = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", DummyClassifier(strategy="most_frequent")),
    ])
    # Fit on trivial data
    dummy.fit([[0] * 9, [1] * 9], [1, 1])
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(dummy, MODEL_PATH)
    logger.warning("Wrote dummy model (single-class dataset) to %s", MODEL_PATH)


if __name__ == "__main__":
    train_and_evaluate()
