# SentinelLens — Setup Guide

## Quick Start (Local Demo — no Splunk required)

```bash
git clone https://github.com/Tahha2003/SentinelLens.git
cd SentinelLens

pip install -r requirements.txt
copy .env.example .env
python eval/train.py
flask --app sentinellens.api.app run --host=0.0.0.0 --port=5000
```

Open **http://localhost:5000** — login: `admin` / `admin123`

Click **Run Pipeline** — 61 incidents from synthetic BOTS data will appear.

---

## Phase 1 — Connect Live Splunk

### Step 1: Install Splunk Enterprise

Download from https://www.splunk.com/en_us/download/splunk-enterprise.html (free trial / dev license).

Default ports after install:
- Web UI: `http://localhost:8000`
- REST API: `https://localhost:8089`

### Step 2: Install BOTS v3 Dataset

1. Download `botsv3_data_set.tgz` — email `bots@splunk.com` for link
2. Extract into `C:\Program Files\Splunk\etc\apps\`
3. Restart Splunk
4. Verify: `index=botsv3 earliest=0 | head 10` in Search & Reporting

### Step 3: Create API Token

1. `localhost:8000` → Settings → Tokens → New Token
2. User: your admin username
3. Audience: `sentinellens-readonly`
4. Expiration: `+90d`
5. Copy the token

### Step 4: Configure .env

```env
SPLUNK_HOST=localhost
SPLUNK_PORT=8089
SPLUNK_TOKEN=<your-token-here>
```

### Step 5: Restart SentinelLens

```bash
flask --app sentinellens.api.app run --host=0.0.0.0 --port=5000
```

Dashboard will show **"Connected to Splunk Live"** green banner.

---

## Phase 2 — MCP Investigation Agent

### Step 1: Install Splunk MCP Server App

1. Go to `localhost:8000` → Apps → Find More Apps
2. Search "MCP Server" → Install `Splunk MCP Server` (v1.3.1+)
3. Or download from https://splunkbase.splunk.com/app/7931

### Step 2: Create MCP Encrypted Token

1. `localhost:8000` → Apps → Splunk MCP Server
2. Click **"Create MCP Encrypted Token"**
3. Copy the encrypted token

### Step 3: Configure .env

```env
SPLUNK_MCP_URL=http://localhost:8000/en-US/splunkd/__raw/services/mcp
SPLUNK_MCP_TOKEN=<your-mcp-encrypted-token>
```

> **Note:** MCP Server requires Splunk Cloud connectivity for OAuth validation.
> On local Enterprise installs, the investigation agent uses `local_mock` fallback
> which generates incident-specific SPL queries without executing them.

### Step 4: Restart and Test

```bash
flask --app sentinellens.api.app run --host=0.0.0.0 --port=5000
```

Open any incident → scroll to **Investigate** panel → type a query.

---

## Docker Setup

```bash
docker compose up --build
```

Open **http://localhost:5000** — same credentials.

---

## Makefile Commands

| Command | Description |
|---------|-------------|
| `make demo` | Train model (if needed) + start dashboard |
| `make eval` | Run eval/train.py — retrain model + write report |
| `make test` | Run pytest with coverage |
| `make lint` | ruff + black + bandit |
| `make docker-up` | Docker compose up |
| `make clean` | Remove cache, DB, coverage files |

---

## Fallback Behavior

If Splunk is unreachable, SentinelLens automatically falls back to local data:

```
SPLUNK_HOST set → health_check() fails → LocalFileDataSource selected
Dashboard shows: "OFFLINE / DEMO MODE" banner
Pipeline runs on: data/bots_sample_events.json (600 synthetic events)
```

To force local mode: leave `SPLUNK_HOST` empty in `.env`.

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DASHBOARD_USER` | No | `admin` | Login username |
| `DASHBOARD_PASSWORD` | **Yes** | `admin123` | Login password — change this |
| `FLASK_SECRET_KEY` | **Yes** | dev default | 32+ char random string |
| `BOTS_DATA_PATH` | No | `data/bots_sample_events.json` | Local data file |
| `MODEL_PATH` | No | `models/scorer_v1.joblib` | Trained model path |
| `CORRELATION_WINDOW_MINUTES` | No | `15` | Sliding window size |
| `MIN_CLUSTER_SIZE` | No | `2` | Min events per incident |
| `SPLUNK_HOST` | Phase 1 | _(empty)_ | Splunk hostname |
| `SPLUNK_PORT` | Phase 1 | `8089` | Splunk REST API port |
| `SPLUNK_TOKEN` | Phase 1 | _(empty)_ | Read-only search token |
| `SPLUNK_MCP_URL` | Phase 2 | _(empty)_ | MCP Server URL |
| `SPLUNK_MCP_TOKEN` | Phase 2 | _(empty)_ | MCP encrypted token |
