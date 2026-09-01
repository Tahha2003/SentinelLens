# SentinelLens API Reference

**Base URL:** `http://localhost:5000`
**Authentication:** HTTP Basic Auth — `admin` / `admin123`
**Format:** All responses are JSON. All errors use `{"error": "message"}`.

---

## System

### GET /api/v1/health

Returns system health status.

**Response 200:**
```json
{
  "status": "ok",
  "datasource": {
    "mode": "splunk_live",
    "healthy": true
  },
  "database": true,
  "scorer_loaded": true,
  "active_model": "98ca94b48b19...",
  "timestamp": "2026-09-01T17:00:00Z"
}
```

`status` is `"degraded"` if scorer model is not loaded.

---

### GET /api/v1/datasource/status

Returns the active data source.

**Response 200:**
```json
{
  "mode": "splunk_live",
  "healthy": true
}
```

`mode` is `"local_bots"` when Splunk is not configured or unreachable.

---

## Incidents

### GET /api/v1/incidents

Paginated list of scored incidents, sorted by score descending.

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | integer | 1 | Page number |
| `limit` | integer | 20 | Results per page (max 100) |
| `min_score` | float | 0.0 | Filter by minimum score |
| `band` | string | — | Filter by `HIGH`, `MEDIUM`, or `LOW` |

**Response 200:**
```json
{
  "data": [
    {
      "incident_id": "d042b145-8fdb-4e9c-9681-121a4127c5a7",
      "score": 1.0,
      "confidence_band": "HIGH",
      "event_count": 169,
      "entity_count": 1,
      "time_start": "2018-08-20T20:17:18+05:00",
      "time_end": "2018-08-20T20:18:00+05:00",
      "top_entities": ["host:frothly-fw1"],
      "severity_max": 2,
      "is_truncated": false,
      "model_version": "98ca94b48b194275..."
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 18,
    "pages": 1
  },
  "datasource_mode": "splunk_live",
  "generated_at": "2026-09-01T17:00:00Z"
}
```

---

### GET /api/v1/incidents/{incident_id}

Full incident detail including cluster and feature data.

**Path Parameters:** `incident_id` (UUID)

**Response 200:**
```json
{
  "incident_id": "d042b145-...",
  "score": 1.0,
  "confidence_band": "HIGH",
  "cluster_id": "a1b2c3d4-...",
  "time_start": "2018-08-20T20:17:18+05:00",
  "time_end": "2018-08-20T20:18:00+05:00",
  "entities": ["host:frothly-fw1"],
  "features": {
    "event_count": 169,
    "event_type_entropy": 0.0,
    "severity_sum": 338,
    "severity_max": 2,
    "entity_fan_out": 1,
    "time_density": 239.1,
    "time_span_minutes": 0.7,
    "unique_sources": 1,
    "perf_deviation_max": null
  },
  "is_truncated": false,
  "model_version": "98ca94b48b19..."
}
```

**Response 404:** Incident not found.

---

### GET /api/v1/incidents/{incident_id}/timeline

All events in the incident cluster, sorted by timestamp ascending.

**Response 200:**
```json
{
  "incident_id": "d042b145-...",
  "count": 169,
  "events": [
    {
      "event_id": "uuid",
      "timestamp": "2018-08-20T20:17:18+05:00",
      "entity_id": "host:frothly-fw1",
      "entity_type": "HOST",
      "event_type": "network_traffic",
      "severity": 2,
      "source": "splunk_live:cisco:asa",
      "raw_fields": { "src_ip": "10.0.0.1", "dest_ip": "54.1.2.3" },
      "tags": []
    }
  ]
}
```

---

### GET /api/v1/incidents/{incident_id}/features

The 9-feature vector used by the ML model for this incident.

**Response 200:**
```json
{
  "incident_id": "d042b145-...",
  "features": {
    "event_count": 169,
    "event_type_entropy": 0.0,
    "severity_sum": 338,
    "severity_max": 2,
    "entity_fan_out": 1,
    "time_density": 239.1,
    "time_span_minutes": 0.7,
    "unique_sources": 1,
    "perf_deviation_max": null
  }
}
```

**Feature Definitions:**

| Feature | Description |
|---------|-------------|
| `event_count` | Total events in cluster |
| `event_type_entropy` | Shannon entropy of event_type distribution — high = diverse attack stages |
| `severity_sum` | Sum of all event severities |
| `severity_max` | Worst-case severity in cluster |
| `entity_fan_out` | Distinct entity count — >3 signals lateral movement |
| `time_density` | Events per minute |
| `time_span_minutes` | Cluster duration |
| `unique_sources` | Cross-source correlation strength |
| `perf_deviation_max` | Max z-score of performance metrics (optional) |

---

## Model

### GET /api/v1/model/report

Returns the active scorer model metrics from `model_registry`.

**Response 200:**
```json
{
  "model_id": "98ca94b48b194275...",
  "algorithm": "logistic_regression",
  "dataset": "bots_v3_synthetic_seed42",
  "precision_val": 1.0,
  "recall_val": 1.0,
  "f1_val": 1.0,
  "confusion_matrix": [[10, 0], [0, 3]],
  "artifact_path": "models/scorer_v1.joblib",
  "trained_at": "2026-08-19T12:52:46Z",
  "is_active": 1
}
```

**Response 503:** No trained model found — run `python eval/train.py`.

---

## Pipeline

### POST /api/v1/pipeline/run

Triggers an async pipeline run. Returns immediately with a `run_id`.

**Response 202:**
```json
{
  "run_id": "f44834e7-af4c-4afb-ad54-8a2b9ca9d735",
  "status": "queued"
}
```

**Response 503:** Scorer model not loaded.

Poll `/api/v1/pipeline/status/{run_id}` to track progress.

---

### GET /api/v1/pipeline/status/{run_id}

**Response 200:**
```json
{
  "run_id": "f44834e7-...",
  "status": "complete",
  "datasource_mode": "splunk_live",
  "event_count": 5000,
  "normalized_count": 5000,
  "cluster_count": 18,
  "normalization_failures": 0,
  "error_message": null,
  "started_at": "2026-09-01T17:28:10Z",
  "completed_at": "2026-09-01T17:29:04Z"
}
```

`status` values: `queued` → `running` → `complete` | `failed`

---

## Investigation

### POST /api/v1/investigate

Submits a natural-language question about an incident. Returns `session_id` immediately — poll for result.

**Request Body:**
```json
{
  "incident_id": "d042b145-8fdb-4e9c-9681-121a4127c5a7",
  "query": "Show network connections for this host"
}
```

**Response 202:**
```json
{
  "session_id": "abc123-...",
  "status": "queued"
}
```

**Response 400:** Missing `incident_id` or `query`.
**Response 404:** Incident not found.

**Agent fallback chain:**
1. `MCPServerAgent` — Splunk MCP Server (translate → execute → summarize)
2. `local_mock` — generates incident-specific SPL without execution

---

### GET /api/v1/investigate/{session_id}

Poll investigation result.

**Response 200 (complete):**
```json
{
  "session_id": "abc123-...",
  "incident_id": "d042b145-...",
  "status": "complete",
  "analyst_query": "Show network connections for this host",
  "spl_generated": "index=botsv3 host=\"frothly-fw1\" earliest=\"2018-08-20T20:17:18+05:00\" latest=\"2018-08-20T20:18:00+05:00\" | stats count by sourcetype, src_ip, dest_ip | sort -count",
  "result_summary": "Investigation query: 'Show network connections for this host'\n\nThis incident involves 1 entities: host:frothly-fw1.\nTime range: 2018-08-20T20:17:18+05:00 to 2018-08-20T20:18:00+05:00.",
  "agent_backend": "local_mock",
  "created_at": "2026-09-01T17:35:00Z",
  "completed_at": "2026-09-01T17:35:01Z"
}
```

`status` values: `queued` → `running` → `complete` | `failed`
`agent_backend` values: `mcp_server` | `local_mock`
