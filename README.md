# SentinelLens

An open-source incident triage copilot for Splunk. Clusters related security events into incidents using entity-centric temporal correlation, scores each incident with a trained ML model, and surfaces them in a ranked dashboard with drill-down timelines.

Built for the **Splunk Agentic Ops Hackathon** — Security Track.

---

## Build Status

| Phase | Status | Summary |
|-------|--------|---------|
| **Phase 0 — Local Pipeline** | ✅ **COMPLETE** | Full local pipeline running — no Splunk required |
| **Phase 1 — Splunk Integration** | ⏳ **PENDING** | Code written, live Splunk connection remaining |
| **Phase 2 — Investigation Agent** | ⏳ **PENDING** | Scaffold ready, MCP Server integration remaining |
| **Phase 3 — Polish & Submission** | ⏳ **PENDING** | Architecture diagram, demo video, OpenAPI spec |

---

## Quick Start (Local Demo — no Splunk required)

```bash
git clone <repo-url>
cd SentinelLens

# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy config
copy .env.example .env

# 3. Train the scoring model
python eval/train.py

# 4. Start the dashboard
flask --app sentinellens.api.app run --host=0.0.0.0 --port=5000
```

Open **http://localhost:5000** — login with `admin` / `admin123`.

Click **Run Pipeline** to process the sample data. 61 incidents will appear ranked by score.

---

## Phase 0 — What Was Built ✅

### 1. Project Scaffold
- Python 3.11 project structure
- `requirements.txt` with pinned versions
- `.env.example` — credentials placeholder, no secrets committed
- `Makefile` — `make demo`, `make test`, `make eval`, `make docker-up`
- `Dockerfile` + `docker-compose.yml`

### 2. Data Contracts (`sentinellens/models.py`)
All dataclasses defined (frozen where appropriate):
- `Event` — normalized security event (UUID4, UTC timestamp, entity_id, severity 1-5)
- `EntityType` — enum: USER, HOST, IP, PROCESS, URL, UNKNOWN
- `MetricPoint` — performance metrics (optional Phase 1 feature)
- `IncidentFeatures` — 9-feature vector (frozen order — ML contract)
- `IncidentCluster` — correlated events group
- `ScoredIncident` — cluster + ML score + confidence band
- `InvestigationResult` — Phase 2 agent response

### 3. Configuration (`sentinellens/config.py`)
- `.env` file loader via `python-dotenv`
- Validation at startup — missing required vars produce a clear error message
- `IS_LOCAL_MODE` flag — auto-detected from environment variables

### 4. Database Layer (`sentinellens/db/`)
**schema.sql** — complete SQLite DDL (7 tables):
- `pipeline_runs` — audit trail for every pipeline execution
- `events` — normalized events (written once, never updated)
- `incident_clusters` — correlation engine output
- `cluster_events` — many-to-many join table
- `scored_incidents` — ML scores per cluster
- `investigation_sessions` — Phase 2 chat history
- `model_registry` — trained model version tracking

**repository.py** — all database operations:
- All queries parameterized — zero SQL string concatenation
- `PRAGMA foreign_keys=ON` applied per-connection (SQLite requirement)
- WAL mode — concurrent reads while pipeline writes
- Retry logic (3 attempts, 100ms backoff) for DB lock errors
- Cascade deletes — no orphan rows possible

### 5. DataSource Layer (`sentinellens/datasource/`)
Critical architecture isolation boundary:

```
DataSource (ABC)
├── LocalFileDataSource   ← BOTS JSON/CSV reads  ✅
├── SplunkDataSource      ← Phase 1 (code ready, needs live instance)  ⏳
└── factory.py            ← Auto-selects: Splunk if configured + healthy, else local
```

- `base.py` — `DataSource` ABC: `get_events()`, `get_metrics()`, `health_check()`, `source_name()`
- `local.py` — JSON/CSV reading, time-window filtering, entity filtering
- `splunk.py` — Splunk Python SDK wrapper (Phase 1 code written)
- `factory.py` — Singleton factory, graceful fallback to local if Splunk is unreachable

**Rule:** No component downstream of this boundary may import `local.py` or `splunk.py` directly. All access goes through `factory.py`. This is what makes Phase 0 a fully standalone deliverable.

### 6. Pipeline (`sentinellens/pipeline/`)

**normalizer.py**
- BOTS + Splunk CIM field mapping table
- `_time` → UTC `datetime` (epoch float and ISO8601 both supported)
- Entity extraction with prefix normalization: `user:alice`, `host:dc01`, `ip:10.0.0.1`
- Severity mapping: string labels and numeric (1-5 range)
- Unknown entity fallback: `unknown:<sha8(raw)>`
- Per-record failure logging — silent failures are tracked and counted, never swallowed

**correlator.py** — Entity-Centric Sliding Window Graph Clustering:
1. Sort events by timestamp ascending
2. Build a NetworkX graph — one node per event
3. Add edges between events in the same entity group within the time window
4. Also link events that reference related entities in raw fields (transitive connectivity)
5. `nx.connected_components()` → incident clusters
6. Filter by `MIN_CLUSTER_SIZE`, cap at `MAX_CLUSTER_SIZE=500`
7. High-activity entity guard: >1000 events for one entity → strict 5-minute window

**features.py** — 9 features (frozen order — changing this requires retraining):

| # | Feature | Description |
|---|---------|-------------|
| 0 | `event_count` | Total events in cluster |
| 1 | `event_type_entropy` | Shannon entropy of event type distribution |
| 2 | `severity_sum` | Sum of all event severities |
| 3 | `severity_max` | Worst-case severity in cluster |
| 4 | `entity_fan_out` | Distinct entity count (>3 signals lateral movement) |
| 5 | `time_density` | Events per minute |
| 6 | `time_span_minutes` | Cluster duration |
| 7 | `unique_sources` | Cross-source correlation strength |
| 8 | `perf_deviation_max` | Max z-score of performance metrics (optional) |

**scorer.py**
- Loads `models/scorer_v1.joblib` at startup
- `predict_proba()` → 0.0–1.0 incident probability score
- Confidence bands: HIGH ≥0.75, MEDIUM ≥0.50, LOW <0.50
- Model file missing → `RuntimeError` with a clear message and fix instruction

**runner.py**
- Async pipeline (background thread) and sync mode (for scripts/CLI)
- Full flow: DataSource → Normalizer → Correlator → Features → Scorer → Repository
- Run status tracked in `pipeline_runs` table, pollable via API

### 7. ML Training (`eval/train.py`)
- Trains both LogisticRegression and GradientBoostingClassifier
- `RANDOM_SEED=42`, `TEST_SPLIT=0.2`, stratified split — fully reproducible
- Selects the algorithm with higher F1 on the held-out set
- Saves winning model to `models/scorer_v1.joblib`
- Writes `eval/scorer_report.md` with measured metrics
- Registers model in `model_registry` DB table

**Evaluation Results (Phase 0 — synthetic data):**

| Metric | Value |
|--------|-------|
| Algorithm selected | Logistic Regression |
| Precision | 1.0000 |
| Recall | 1.0000 |
| F1 | 1.0000 |
| Test set size | 13 samples (stratified 80/20 split) |
| Training dataset | 600 synthetic BOTS-style events |

> Note: F1=1.0 is expected on synthetic data with clean, well-separated attack patterns. Metrics on real BOTS v3 data will be lower and will be reported honestly when available.

### 8. Sample Data (`data/bots_sample_events.json`)
600 synthetic BOTS-style events — runs out of the box with no external dependencies:
- **400 noise events** (label=0) — normal web traffic, routine logins, AWS API calls
- **200 incident events** (label=1) — six attack scenarios:

| Attack Scenario | Primary Entity | Description |
|----------------|----------------|-------------|
| Brute Force | `wrstock` from `23.22.63.114` | 46 failed logins against `venus.buttercupgames.com` |
| Lateral Movement | `bob` | Authenticated to dc01 → fileserver01 → appserver02 within 15 min |
| C2 Beaconing | `workstation07` | Periodic HTTP POST to `185.220.101.45` every ~2 min over 30 min |
| Data Exfiltration | `fileserver01` | Large TCP transfers (1–5 MB each) to `104.21.44.102` |
| Malware Detection | `workstation07`, `workstation12` | Symantec AV alerts — CobaltStrike, WannaCry, Backdoor.Tidserv |
| DNS Tunneling | `workstation07` | Long hex subdomain TXT queries to external resolvers |

### 9. REST API (`sentinellens/api/`)
All endpoints protected by HTTP Basic Auth — including `/health`:

| Method | Endpoint | Phase | Description |
|--------|----------|-------|-------------|
| GET | `/api/v1/health` | 0 | System health — datasource, scorer, DB status |
| GET | `/api/v1/incidents` | 0 | Paginated incident list, sorted by score DESC |
| GET | `/api/v1/incidents/<id>` | 0 | Single incident with full cluster detail |
| GET | `/api/v1/incidents/<id>/timeline` | 0 | All events sorted by timestamp |
| GET | `/api/v1/incidents/<id>/features` | 0 | 9-feature vector for explainability |
| GET | `/api/v1/model/report` | 0 | Active model metrics from model_registry |
| POST | `/api/v1/pipeline/run` | 0 | Trigger pipeline run (async, returns run_id immediately) |
| GET | `/api/v1/pipeline/status/<run_id>` | 0 | Poll pipeline run status |
| GET | `/api/v1/datasource/status` | 1 | Active datasource mode (live or offline) |
| POST | `/api/v1/investigate` | 2 | Submit NL query (returns session_id; local mock in Phase 0) |
| GET | `/api/v1/investigate/<session_id>` | 2 | Poll investigation result |

### 10. Dashboard (`templates/`)
HTMX + Jinja2 server-rendered UI — no React, no JavaScript build step:

- **Incidents List** — score bar, confidence band badge, event count, top entities, duration
- **Pipeline Button** — triggers pipeline via HTMX, shows status inline
- **Incident Detail** — full feature vector table, entity badges, event timeline
- **Investigation Panel** — natural language query input, real-time result polling, SPL display
- **OFFLINE MODE banner** — clearly shown when Splunk is not connected
- **Dark theme** (GitHub-style color scheme)

### 11. Security
- HTTP Basic Auth on every route — no unauthenticated reads of security data
- All SQL parameterized — zero string concatenation, enforced by `bandit`
- `.env` in `.gitignore` — credentials are never committed
- Splunk token is read-only (search only, no write/delete)
- No auto-remediation — the system is fully read-only against Splunk

---

## Phase 1 — Splunk Integration (PENDING) ⏳

**What is already written:**
- `sentinellens/datasource/splunk.py` — full `SplunkDataSource` implementation
- `factory.py` — auto-selects Splunk when `SPLUNK_HOST` + `SPLUNK_TOKEN` are set
- Graceful fallback: Splunk unreachable → silently switch to local mode → show "OFFLINE MODE" banner
- `/api/v1/datasource/status` endpoint live

**What remains to be done:**
- [ ] Apply for Splunk dev license — https://dev.splunk.com (free, just admin time)
- [ ] Connect to a live Splunk instance and run the pipeline end-to-end
- [ ] Set `SPLUNK_HOST`, `SPLUNK_PORT`, `SPLUNK_TOKEN` in `.env`
- [ ] Verify fallback: kill Splunk mid-session → dashboard stays live with local data
- [ ] Optional: Splunk UF + OS metrics add-on → feed `perf_deviation_max` feature

**To enable:**
```env
SPLUNK_HOST=your-splunk-host.example.com
SPLUNK_PORT=8089
SPLUNK_TOKEN=your-read-only-search-token
```

---

## Phase 2 — Investigation Agent (PENDING) ⏳

**What is already written:**
- `sentinellens/agent/base.py` — `InvestigationAgent` ABC
- `sentinellens/agent/mcp_agent.py` — `MCPServerAgent` (translate NL → SPL → execute → summarize)
- `/api/v1/investigate` endpoint — wired up, returns local mock response in Phase 0
- Dashboard investigation panel — query input, result display with SPL transparency

**What remains to be done:**
- [ ] Obtain Splunk MCP Server URL
- [ ] Test `MCPServerAgent` against a live MCP Server
- [ ] Write `SplunkSDKAgent` as a fallback (if MCP is unstable)
- [ ] Run agent evaluation — 15 fixed test questions, manual scoring → `eval/agent_eval.md`
- [ ] Set `SPLUNK_MCP_URL` in `.env`

**To enable:**
```env
SPLUNK_MCP_URL=https://your-mcp-server-url
```

---

## Phase 3 — Polish & Submission (PENDING) ⏳

- [ ] Architecture diagram (PNG/SVG) — drawn from the actual built system, not aspirational
- [ ] `SETUP.md` — Splunk integration guide with screenshots
- [ ] OpenAPI spec — generated from Flask routes via `flask-openapi3`
- [ ] Demo video — under 3 minutes: `make demo` → dashboard → incident drill-down → investigate query
- [ ] `pytest` coverage ≥80% on correlator and scorer
- [ ] MIT license SPDX headers on all source files
- [ ] Final repo cleanup — no dead code, no credentials, no TODOs in tests

---

## Architecture

```
┌─────────────────────┐    ┌──────────────────────────────────────────────────────────┐
│   Data Sources      │    │                     Core Pipeline                         │
│                     │    │                                                            │
│  LocalFileDataSource├───►│  Normalizer → Correlator → FeatureExtractor → Scorer      │
│  (Phase 0 ✅)       │    │                     │                                      │
│                     │    │                     ▼                                      │
│  SplunkDataSource   │    │              Repository (SQLite WAL)                      │
│  (Phase 1 ⏳)       │    │                     │                                      │
│                     │    │                     ▼                                      │
└─────────────────────┘    │          REST API (Flask + Basic Auth)                    │
        ▲                  │                     │                                      │
        │ factory.py       │                     ▼                                      │
        │ auto-selects     │           Dashboard (HTMX + Jinja2)                       │
                           │                     │                                      │
                           │                     ▼                                      │
                           │       InvestigationAgent (Phase 2 ⏳)                     │
                           │       MCPServerAgent / SplunkSDKAgent                     │
                           └──────────────────────────────────────────────────────────┘
```

---

## Repository Structure

```
SentinelLens/
├── sentinellens/
│   ├── models.py              # All dataclasses — Event, IncidentCluster, ScoredIncident...
│   ├── config.py              # .env loader + startup validation
│   ├── datasource/
│   │   ├── base.py            # DataSource ABC (critical isolation boundary)
│   │   ├── local.py           # LocalFileDataSource ✅
│   │   ├── splunk.py          # SplunkDataSource ⏳ (code ready, needs live test)
│   │   └── factory.py         # Auto-selects correct datasource
│   ├── pipeline/
│   │   ├── normalizer.py      # BOTS + CIM field mapping
│   │   ├── correlator.py      # NetworkX entity graph clustering
│   │   ├── features.py        # 9-feature vector extraction
│   │   ├── scorer.py          # ML model prediction
│   │   └── runner.py          # Pipeline orchestrator (async + sync modes)
│   ├── agent/
│   │   ├── base.py            # InvestigationAgent ABC
│   │   └── mcp_agent.py       # MCPServerAgent ⏳
│   ├── api/
│   │   ├── app.py             # Flask application factory
│   │   ├── auth.py            # HTTP Basic Auth middleware
│   │   └── routes/
│   │       ├── health.py
│   │       ├── incidents.py
│   │       ├── pipeline.py
│   │       └── investigate.py
│   └── db/
│       ├── schema.sql          # Full SQLite DDL — 7 tables
│       └── repository.py       # All DB operations — parameterized SQL only
├── templates/
│   ├── base.html               # Dark theme, HTMX CDN, navigation
│   ├── incidents.html          # Ranked incident list dashboard
│   └── incident_detail.html    # Timeline + features + investigation panel
├── data/
│   ├── bots_sample_events.json # 600 synthetic BOTS events — runs out of the box
│   └── README.md               # Data attribution and scenario descriptions
├── eval/
│   ├── train.py                # Reproducible ML training script
│   └── scorer_report.md        # Measured precision / recall / F1
├── models/
│   └── scorer_v1.joblib        # Trained model artifact (generated by eval/train.py)
├── .env.example                # Config template — no secrets, safe to commit
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── requirements.txt            # Pinned production dependencies
├── requirements-dev.txt        # pytest, black, ruff, bandit
└── LICENSE                     # MIT
```

---

## Configuration Reference

| Variable | Phase | Required | Default | Description |
|----------|-------|----------|---------|-------------|
| `DASHBOARD_USER` | 0 | No | `admin` | Dashboard login username |
| `DASHBOARD_PASSWORD` | 0 | **Yes** | `admin123` | Dashboard login password — change this |
| `FLASK_SECRET_KEY` | 0 | **Yes** | dev default | Flask session secret (use 32+ random chars in production) |
| `BOTS_DATA_PATH` | 0 | No | `data/bots_sample_events.json` | Path to local BOTS data file |
| `MODEL_PATH` | 0 | No | `models/scorer_v1.joblib` | Path to trained scorer model |
| `CORRELATION_WINDOW_MINUTES` | 0 | No | `15` | Sliding time window for event correlation |
| `MIN_CLUSTER_SIZE` | 0 | No | `2` | Minimum events required to form an incident |
| `SPLUNK_HOST` | 1 | No | _(empty)_ | Splunk instance hostname |
| `SPLUNK_PORT` | 1 | No | `8089` | Splunk REST API port |
| `SPLUNK_TOKEN` | 1 | No | _(empty)_ | Read-only search token |
| `SPLUNK_MCP_URL` | 2 | No | _(empty)_ | Splunk MCP Server URL |

---

## Makefile Commands

```bash
make demo        # Train model (if needed) + start dashboard at localhost:5000
make eval        # Run eval/train.py — train model and write scorer_report.md
make test        # Run pytest with coverage report
make lint        # ruff check + black --check + bandit security scan
make docker-up   # docker compose up --build
make clean       # Remove __pycache__, *.db, coverage files
```

---

## License

MIT — see [LICENSE](LICENSE)
