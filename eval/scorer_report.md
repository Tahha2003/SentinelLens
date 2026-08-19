# SentinelLens Scorer Evaluation Report

**Generated:** 2026-08-19T12:52:46.293797+00:00
**Random seed:** 42
**Test split:** 0.2 (stratified)
**Dataset:** data/bots_sample_events.json

---

## Selected Model

**Algorithm:** `logistic_regression`
**Model hash (SHA256):** `98ca94b48b194275492ba6ada51f527d6ef534c29fd1a2fe804212d87e9a726b`
**Artifact:** `models\scorer_v1.joblib`

| Metric    | Value  |
|-----------|--------|
| Precision | 1.0000 |
| Recall    | 1.0000 |
| F1        | 1.0000 |

### Classification Report

```
              precision    recall  f1-score   support

           0       1.00      1.00      1.00        10
           1       1.00      1.00      1.00         3

    accuracy                           1.00        13
   macro avg       1.00      1.00      1.00        13
weighted avg       1.00      1.00      1.00        13

```

### Confusion Matrix

```
              Predicted
              Noise  Incident
Actual Noise    10       0
       Incident 0       3
```

---

## Comparison: Both Algorithms

| Algorithm             | Precision | Recall | F1     |
|-----------------------|-----------|--------|--------|
| logistic_regression   | 1.0000    | 1.0000 | 1.0000 | ← SELECTED |
| gradient_boosting     | 1.0000    | 1.0000 | 1.0000 |

---

## Feature Vector (frozen order)

| # | Feature              |
|---|----------------------|
| 0 | `event_count` |
| 1 | `event_type_entropy` |
| 2 | `severity_sum` |
| 3 | `severity_max` |
| 4 | `entity_fan_out` |
| 5 | `time_density` |
| 6 | `time_span_minutes` |
| 7 | `unique_sources` |
| 8 | `perf_deviation_max` |

---

> **Note:** All metrics are computed on the held-out test split.
> No metric in this report was hand-written or estimated.
> Reproduce by running: `python eval/train.py`