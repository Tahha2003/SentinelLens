# SentinelLens — System Architecture

## Overview

SentinelLens is built around a strict layered architecture with one load-bearing rule:
**no component downstream of the DataSource interface may import `local.py` or `splunk.py` directly.**
This single constraint makes Phase 0 a fully standalone deliverable independent of Splunk.

---

## Full System Diagram

```mermaid
flowchart TB
    subgraph SOURCES["Data Sources (Layer 0)"]
        LOCAL["LocalFileDataSource\n(BOTS JSON/CSV)\n✅ Phase 0"]
        SPLUNK["SplunkDataSource\n(REST API · index=botsv3)\n✅ Phase 1"]
    end

    FACTORY["factory.py\nAuto-selects: Splunk if healthy,\nelse Local\n(OFFLINE MODE banner)"]

    subgraph PIPELINE["Core Pipeline (Layer 1-2)"]
        NORM["EventNormalizer\nBOTS + CIM field mapping\n→ Event dataclass"]
        CORR["EntityCorrelator\nNetworkX sliding window\ngraph clustering"]
        FEAT["FeatureExtractor\n9-feature vector\n(frozen ML contract)"]
        SCORE["IncidentScorer\nLogistic Regression\nF1=1.0 on held-out set"]
    end

    subgraph DB["Repository (SQLite WAL)"]
        EVENTS["events table"]
        CLUSTERS["incident_clusters"]
        SCORED["scored_incidents"]
        RUNS["pipeline_runs"]
    end

    subgraph API["REST API (Layer 3)"]
        HEALTH["GET /api/v1/health"]
        INC["GET /api/v1/incidents"]
        PIPE["POST /api/v1/pipeline/run"]
        INV["POST /api/v1/investigate"]
    end

    subgraph DASH["Dashboard (HTMX + Jinja2)"]
        LIST["Incident List\nScore bars · Band badges\nEntity · Duration"]
        DETAIL["Incident Detail\nEvent Timeline\nFeature Vector"]
        CHAT["Investigation Panel\nNL Query → SPL\nResult Summary"]
    end

    subgraph AGENT["Investigation Agent (Layer 4)"]
        MCP["MCPServerAgent\nSplunk MCP Server\n⏳ Phase 2"]
        SDK["SplunkSDKAgent\nDirect SPL execution\n(fallback)"]
        MOCK["LocalMockAgent\nSmart SPL generation\n(demo fallback)"]
    end

    LOCAL --> FACTORY
    SPLUNK --> FACTORY
    FACTORY --> NORM
    NORM --> CORR
    CORR --> FEAT
    FEAT --> SCORE
    SCORE --> DB
    NORM --> DB
    DB --> API
    API --> DASH
    INV --> AGENT
    MCP -->|"fails"| SDK
    SDK -->|"fails"| MOCK
```

---

## Request Flow (End to End)

```mermaid
sequenceDiagram
    participant Analyst
    participant Dashboard
    participant API
    participant Pipeline
    participant Splunk
    participant DB

    Analyst->>Dashboard: Click "Run Pipeline"
    Dashboard->>API: POST /api/v1/pipeline/run
    API-->>Dashboard: 202 {run_id}
    Dashboard->>Dashboard: Show "Running..." status

    API->>Pipeline: PipelineRunner.run_async()
    Pipeline->>Splunk: GET index=botsv3 earliest=0 (5000 events)
    Splunk-->>Pipeline: Raw event JSON
    Pipeline->>Pipeline: Normalize → Correlate → Score
    Pipeline->>DB: INSERT events, clusters, incidents

    Analyst->>Dashboard: Refresh / auto-reload
    Dashboard->>API: GET /api/v1/incidents
    API->>DB: SELECT scored_incidents JOIN clusters
    DB-->>API: 18 incidents sorted by score DESC
    API-->>Dashboard: JSON response
    Dashboard-->>Analyst: Ranked incident list

    Analyst->>Dashboard: Click "View →" on incident
    Dashboard->>API: GET /api/v1/incidents/{id}/timeline
    API->>DB: SELECT events WHERE cluster_id=...
    DB-->>API: Events sorted by timestamp
    API-->>Dashboard: Event timeline
    Dashboard-->>Analyst: Timeline + features + investigate panel
```

---

## Component Dependency Map

```
Module                  May Import From              May NOT Import From
────────────────────────────────────────────────────────────────────────
api/routes/*.py      →  pipeline/, db/, models.py   datasource/local.py directly
pipeline/correlator  →  models.py, features.py      datasource/*, db/*, agent/*
pipeline/scorer      →  models.py, features.py      datasource/*, db/*, api/*
pipeline/normalizer  →  models.py, datasource/base  datasource/local.py directly
datasource/splunk    →  datasource/base, models.py  pipeline/*, db/*, api/*
agent/mcp_agent      →  agent/base, models.py       datasource/*, pipeline/*
```

---

## Data Flow

```
Raw Events (JSON/CSV or Splunk)
        │
        ▼
  EventNormalizer
  ├── _time → UTC datetime
  ├── entity_id → "user:alice", "host:dc01", "ip:10.0.0.1"
  ├── event_type → CIM-normalized
  └── severity → 1-5
        │
        ▼
  EntityCorrelator (NetworkX)
  ├── Sort by timestamp
  ├── Group by entity_id
  ├── Add edges within 15-min window
  ├── connected_components() → clusters
  └── Filter: min_size=2, cap=500
        │
        ▼
  FeatureExtractor (9 features)
  ├── event_count, event_type_entropy
  ├── severity_sum, severity_max
  ├── entity_fan_out, time_density
  ├── time_span_minutes, unique_sources
  └── perf_deviation_max (optional)
        │
        ▼
  IncidentScorer (Logistic Regression)
  ├── predict_proba() → 0.0–1.0
  └── HIGH ≥0.75 | MEDIUM ≥0.50 | LOW <0.50
        │
        ▼
  SQLite Repository → REST API → HTMX Dashboard
```

---

## Technology Stack

| Layer | Technology | Version | Justification |
|-------|-----------|---------|---------------|
| Runtime | Python | 3.11+ | scikit-learn/networkx ecosystem |
| API Server | Flask | 3.0.3 | Minimal overhead, fast to build |
| Graph Clustering | NetworkX | 3.3 | Native connected_components algorithm |
| ML Scoring | scikit-learn | 1.5.1 | LR + GBT, joblib serialization |
| Storage | SQLite WAL | built-in | Zero deployment overhead |
| Frontend | HTMX + Jinja2 | 1.9+ | No React build step needed |
| Splunk Integration | REST API | v1 | Direct HTTP, avoids SDK parser issues |
| MCP Server | Splunk MCP | 1.3.1 | Hackathon bounty target |

---

## Deployment

```
┌─────────────────────────────────────────────────┐
│  Developer Machine / Demo Environment            │
│                                                  │
│  ┌─────────────────┐   ┌─────────────────────┐  │
│  │  SentinelLens   │   │   Splunk Enterprise  │  │
│  │  Flask :5000    │◄──│   localhost:8000     │  │
│  │  SQLite WAL     │   │   REST API :8089     │  │
│  │                 │   │   index=botsv3       │  │
│  └─────────────────┘   │   MCP Server v1.3.1  │  │
│                        └─────────────────────┘  │
│                                                  │
│  make demo → http://localhost:5000               │
│  Login: admin / admin123                         │
└─────────────────────────────────────────────────┘
```
