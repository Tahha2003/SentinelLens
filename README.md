# SentinelLens

> An open-source incident triage copilot for Splunk — built for the **Splunk Agentic Ops Hackathon, Security Track**.

SentinelLens clusters raw security events into incident-level groupings using entity-centric temporal correlation, scores each incident with a trained ML model, and lets analysts investigate incidents through a natural-language interface with auto-generated SPL queries.

---

## Build Status

| Phase | Status | Description |
|-------|--------|-------------|
| **Phase 0 — Local Pipeline** | ✅ **Complete** | Full pipeline on synthetic BOTS data — no Splunk required |
| **Phase 1 — Splunk Integration** | ✅ **Complete** | Live Splunk connection, real BOTS v3 data, 18 incidents |
| **Phase 2 — Investigation Agent** | ✅ **Complete** | NL → SPL generation, incident-specific queries, mock fallback |
| **Phase 3 — Submission Polish** | ✅ **Complete** | Architecture diagram, OpenAPI spec, agent eval, this README |

---

## Quick Start

```bash
git clone https://github.com/Tahha2003/SentinelLens.git
cd SentinelLens

pip install -r requirements.txt
copy .env.example .env

python eval/train.py

flask --app sentinellens.api.app run --host=0.0.0.0 --port=5000
```

Open **http://localhost:5000** — login: `admin` / `admin123`

Click **Run Pipeline** → incidents appear ranked by model score.

> Full Splunk setup: see [SETUP.md](SETUP.md)

---

## What It Does

### Problem
Organizations running base-tier Splunk Enterprise/Cloud (without the premium ES SKU) have no agentic triage capability. Analysts manually cross-reference events across multiple ad-hoc searches to determine whether a set of alerts represents one incident, multiple incidents, or noise — for every alert, every shift.

### Solution
SentinelLens provides three capabilities on top of standard Splunk:

1. **Incident Clustering** — Groups related events into entity-centric incident clusters using a sliding-window graph algorithm (NetworkX connected components)
2. **ML Scoring** — Scores each cluster with a trained Logistic Regression model, ranked by probability of being a real incident
3. **NL Investigation** — Analyst types a question in plain English, SentinelLens generates incident-specific SPL and (when Splunk MCP Server is available) executes and summarizes the results

---

## Live Results (BOTS v3 Dataset)

| Metric | Value |
|--------|-------|
| Events fetched from Splunk | 5,000 |
| Normalization failures | 0 |
| Incident clusters produced | 18 |
| HIGH confidence incidents | 17 |
| Top incident score | 1.000 |
| Pipeline runtime | ~2 minutes |
| Datasource | `index=botsv3` — Splunk Enterprise local |

**Scorer evaluation (held-out test split, synthetic data):**

| Metric | Value |
|--------|-------|
| Algorithm | Logistic Regression |
| Precision | 1.0000 |
| Recall | 1.0000 |
| F1 | 1.0000 |
| Test set | 13 samples (80/20 stratified split, seed=42) |

> See [eval/scorer_report.md](eval/scorer_report.md) for full confusion matrix and methodology.
> F1=1.0 reflects clean synthetic data — real BOTS v3 metrics will be lower and reported honestly.

**Investigation agent evaluation (15 test questions, manual scoring):**

| Rating | Count | % |
|--------|-------|---|
| Correct SPL | 8 | 53% |
| Relevant/Partial | 6 | 40% |
| Incorrect | 1 | 7% |

> See [eval/agent_eval.md](eval/agent_eval.md) for full question set and analysis.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Data Sources                                 │
│                                                                       │
│   LocalFileDataSource ──┐                                            │
│   (BOTS JSON/CSV)       ├──► factory.py (auto-selects)              │
│   ✅ Phase 0            │                                            │
│                         │                                            │
│   SplunkDataSource ─────┘                                            │
│   (REST API, index=botsv3)                                           │
│   ✅ Phase 1                                                         │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Core Pipeline                                  │
│                                                                       │
│   EventNormalizer → EntityCorrelator → FeatureExtractor → Scorer    │
│   (BOTS+CIM map)    (NetworkX graph)   (9-feature vec)   (LR/GBT)  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌──────────────────┐    ┌──────────────────────────────────────────────┐
│  SQLite WAL DB   │◄───│           REST API (Flask + Basic Auth)      │
│  7 tables        │    │           11 endpoints                        │
└──────────────────┘    └──────────────────────┬───────────────────────┘
                                               │
                                               ▼
                               ┌───────────────────────────┐
                               │  HTMX Dashboard            │
                               │  Incident list · Timeline  │
                               │  Investigation panel        │
                               └──────────────┬────────────┘
                                              │
                                              ▼
                               ┌───────────────────────────┐
                               │  Investigation Agent       │
                               │  MCPServerAgent (Phase 2)  │
                               │  → SplunkSDKAgent          │
                               │  → LocalMockAgent          │
                               └───────────────────────────┘
```

Full diagram with sequence flow and component map: [docs/architecture.md](docs/architecture.md)

---

## Repository Structure

```
SentinelLens/
├── sentinellens/
│   ├── models.py              # Event, IncidentCluster, ScoredIncident dataclasses
│   ├── config.py              # .env loader + validation
│   ├── datasource/
│   │   ├── base.py            # DataSource ABC (isolation boundary)
│   │   ├── local.py           # LocalFileDataSource ✅
│   │   ├── splunk.py          # SplunkDataSource ✅
│   │   └── factory.py         # Auto-selects correct datasource
│   ├── pipeline/
│   │   ├── normalizer.py      # BOTS + CIM field mapping
│   │   ├── correlator.py      # NetworkX entity graph clustering
│   │   ├── features.py        # 9-feature vector (frozen ML contract)
│   │   ├── scorer.py          # ML model prediction
│   │   └── runner.py          # Async + sync pipeline orchestrator
│   ├── agent/
│   │   ├── base.py            # InvestigationAgent ABC
│   │   └── mcp_agent.py       # MCPServerAgent (Phase 2)
│   ├── api/
│   │   ├── app.py             # Flask application factory
│   │   ├── auth.py            # HTTP Basic Auth middleware
│   │   └── routes/            # health, incidents, pipeline, investigate
│   └── db/
│       ├── schema.sql          # SQLite DDL — 7 tables
│       └── repository.py       # All DB ops — parameterized SQL only
├── templates/
│   ├── base.html               # Dark theme, HTMX, navigation
│   ├── incidents.html          # Ranked incident dashboard
│   └── incident_detail.html    # Timeline + features + NL investigation
├── data/
│   ├── bots_sample_events.json # 600 synthetic BOTS events (out-of-the-box demo)
│   └── README.md
├── eval/
│   ├── train.py                # Reproducible ML training (LR vs GBT, seed=42)
│   ├── scorer_report.md        # Measured precision/recall/F1 ✅
│   └── agent_eval.md           # 15 NL query manual evaluation ✅
├── models/
│   └── scorer_v1.joblib        # Trained model artifact
├── docs/
│   ├── architecture.md         # Full system diagram (Mermaid) ✅
│   ├── openapi.json            # OpenAPI 3.0 spec ✅
│   └── api-reference.md        # Human-readable API reference ✅
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── Makefile
├── SETUP.md                    # Splunk integration guide ✅
├── requirements.txt
└── LICENSE
```

---

## API Reference

All endpoints require HTTP Basic Auth (`admin` / `admin123`).

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/health` | System health — datasource, scorer, DB |
| GET | `/api/v1/incidents` | Paginated incidents, sorted by score DESC |
| GET | `/api/v1/incidents/<id>` | Incident detail with cluster |
| GET | `/api/v1/incidents/<id>/timeline` | Events sorted by timestamp |
| GET | `/api/v1/incidents/<id>/features` | 9-feature vector (explainability) |
| GET | `/api/v1/model/report` | Active model precision/recall/F1 |
| POST | `/api/v1/pipeline/run` | Trigger async pipeline run |
| GET | `/api/v1/pipeline/status/<run_id>` | Poll pipeline status |
| GET | `/api/v1/datasource/status` | Active datasource mode |
| POST | `/api/v1/investigate` | Submit NL investigation query |
| GET | `/api/v1/investigate/<session_id>` | Poll investigation result |

Full OpenAPI 3.0 spec: [docs/openapi.json](docs/openapi.json)

---

## Configuration

Copy `.env.example` to `.env`:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DASHBOARD_PASSWORD` | **Yes** | `admin123` | Change before any real deployment |
| `FLASK_SECRET_KEY` | **Yes** | dev default | 32+ random chars in production |
| `BOTS_DATA_PATH` | No | `data/bots_sample_events.json` | Local data file |
| `MODEL_PATH` | No | `models/scorer_v1.joblib` | Trained scorer |
| `SPLUNK_HOST` | Phase 1 | _(empty)_ | Splunk hostname |
| `SPLUNK_TOKEN` | Phase 1 | _(empty)_ | Read-only search token |
| `SPLUNK_MCP_URL` | Phase 2 | _(empty)_ | MCP Server URL |
| `SPLUNK_MCP_TOKEN` | Phase 2 | _(empty)_ | MCP encrypted token |

---

## Splunk Integration Details

### Data Source (Phase 1)
- Connects to `https://<host>:8089` using Splunk REST API
- Default SPL: `search index=botsv3 earliest=0 | head 5000`
- Uses Bearer token auth — no SDK parser (avoids binary field encoding issues in BOTS v3)
- Graceful fallback: Splunk unreachable → local data → "OFFLINE MODE" banner

### MCP Server (Phase 2)
- App: `Splunk MCP Server` v1.3.1 installed from Splunkbase
- Endpoint: `http://localhost:8000/en-US/splunkd/__raw/services/mcp`
- Authentication: encrypted token (created from MCP Server app UI)
- Fallback chain: `MCPServerAgent` → `local_mock`

> On local Splunk Enterprise installs, MCP OAuth validation requires Splunk Cloud
> connectivity. When unavailable, `local_mock` generates incident-specific SPL
> queries per FR2.3 (graceful degradation).

---

## Key Design Decisions

### DataSource Isolation
`LocalFileDataSource` and `SplunkDataSource` both implement the same `DataSource` ABC. No downstream component imports either directly — all access goes through `datasource/factory.py`. This is what makes Phase 0 a complete standalone deliverable independent of Splunk.

### Deterministic Cluster IDs
Cluster IDs are generated from `md5(entity_id + time_start)` — the same cluster of events always produces the same ID. Combined with `INSERT OR IGNORE`, running the pipeline multiple times never creates duplicate incidents.

### ML Feature Contract
`IncidentFeatures.to_vector()` order is frozen. Changing it without retraining the model produces silently wrong scores. The 9-feature order is documented in [docs/architecture.md](docs/architecture.md).

---

## Makefile Commands

```bash
make demo        # Train model + start dashboard at localhost:5000
make eval        # Retrain model, write eval/scorer_report.md
make test        # pytest with coverage
make lint        # ruff + black + bandit
make docker-up   # docker compose up --build
make clean       # Remove cache, DB, coverage files
```

---

## Hackathon Deliverables

| Item | Status | Location |
|------|--------|----------|
| Public GitHub repo, MIT license | ✅ | https://github.com/Tahha2003/SentinelLens |
| README with setup instructions | ✅ | This file |
| requirements.txt | ✅ | `requirements.txt` |
| Architecture diagram | ✅ | `docs/architecture.md` |
| Sample data (no Splunk needed) | ✅ | `data/bots_sample_events.json` |
| API documentation (OpenAPI) | ✅ | `docs/openapi.json` |
| Evaluation report (precision/recall/F1) | ✅ | `eval/scorer_report.md` |
| Agent evaluation (manual scoring) | ✅ | `eval/agent_eval.md` |
| Demo video (<3 min) | ⏳ | Pending — see script below |

### Demo Video Script

1. `make demo` → dashboard loads at localhost:5000
2. Show **"Connected to Splunk Live"** banner
3. Click **Run Pipeline** → show "Running…" → wait ~2 min → 18 incidents
4. Scroll the incident list — score bars, HIGH badges, BOTS hostnames
5. Click **View →** on `host:frothly-fw1` → 169-event timeline, Cisco ASA logs
6. Scroll to **Investigate** → type `"Show network connections"` → generated SPL
7. Type `"Show failed logins"` → `EventCode=4625` SPL with entity + time range
8. Back to dashboard → click Health — show datasource, model, DB status

---

## License

MIT — see [LICENSE](LICENSE)

---

## Security Notes

- HTTP Basic Auth on every route including `/health`
- All SQL parameterized — zero string concatenation
- `.env` in `.gitignore` — no credentials committed
- Splunk token is read-only (search only, no write/delete/execute)
- No auto-remediation — system is fully read-only against Splunk
