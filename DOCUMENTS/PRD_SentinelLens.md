# Product Requirements Document: SentinelLens

**Project codename:** SentinelLens (formerly "ThreatGuard AI")
**Event:** Splunk Agentic Ops Hackathon
**Track:** Security
**Document status:** Draft v1 — for team alignment before build start
**Owner:** [team lead name]
**Date:** June 14, 2026

---

## 1. Summary

SentinelLens is an open-source incident triage copilot for Splunk. It clusters related security events into incident-level groupings using entity-centric temporal correlation, scores each incident using a model trained and evaluated on a real labeled dataset, and lets analysts investigate incidents through a natural-language agent built on Splunk's AI Assistant and MCP Server.

The system is built **local-first**: core detection, correlation, and scoring logic is developed and validated against a static labeled dataset (Splunk's Boss of the SOC data) before any live Splunk connection is introduced. Splunk integration is added behind a swappable data-source interface in a later phase, so the project has a working, demoable state at every stage of the build.

---

## 2. Problem Statement

### 2.1 The problem we are NOT solving (and why)

"Alert fatigue / 90% false positives" is the standard framing used across the AI-SOC market in 2026 and is no longer differentiated — every major vendor (Microsoft, Palo Alto, CrowdStrike, Dropzone AI, Hunto AI, AirMDR, Stellar Cyber) leads with this exact claim, and Cisco has announced native agentic triage for Splunk Enterprise Security itself. We will not pitch this as our core problem statement, and we will not publish unverified accuracy/reduction percentages.

### 2.2 The problem we ARE solving

Organizations running **base-tier Splunk Enterprise/Cloud** (not the premium Enterprise Security SKU, and not a $30k+/year third-party AI-SOC platform) have no agentic triage capability. Their analysts manually cross-reference events across multiple ad-hoc searches to determine whether a set of alerts represents one incident, multiple incidents, or noise — for every alert, every shift.

This is a real, narrow, defensible gap: enterprise-tier orgs get native agents; small/mid-market Splunk users do not, and the cost of the existing alternatives puts them out of reach.

### 2.3 Target users

- Small security teams (1-5 analysts) running Splunk Enterprise/Cloud without ES.
- MSSPs running Splunk across multiple smaller client environments.
- For the hackathon itself: the judging panel and Splunk's developer ecosystem (Splunkbase, dev.splunk.com) — this audience cares about depth of Splunk AI-stack integration specifically.

---

## 3. Goals and Non-Goals

### 3.1 Goals

- G1: Cluster raw security events into entity-centric "incidents" using temporal + relational correlation.
- G2: Score each incident with a model trained and evaluated against a real labeled dataset, with reported precision/recall — not invented percentages.
- G3: Provide a dashboard showing ranked incidents with drill-down to constituent events and a timeline view.
- G4: Provide a natural-language investigation agent that translates analyst questions into Splunk queries via Splunk's AI Assistant / MCP Server, executes them, and summarizes results.
- G5: Run fully on local data with zero Splunk dependency (Phase 0), then swap to a live Splunk backend without changing any downstream component (Phase 1+).
- G6: Produce all hackathon-required deliverables: demo video (<3 min), public MIT-licensed repo, README, architecture diagram, sample data, API docs.

### 3.2 Non-Goals (explicitly out of scope for this build)

- NG1: We are not building a SOAR/auto-remediation system. No automated response actions (blocking IPs, disabling accounts, etc.).
- NG2: We are not claiming production-readiness, a specific accuracy target, or a specific cost/time-savings figure unless it is measured during the build and reproducible by a third party.
- NG3: We are not building multi-tenant support, RBAC, or enterprise auth (SSO/SAML) — single-user/single-org demo scope only.
- NG4: We are not committing to a business model, customer acquisition plan, or pricing as part of this submission. (See "Idea Validation" notes — addressed separately, not part of product scope.)
- NG5: "System performance correlation" (CPU/memory/disk as a primary attack signal) is **not** a core mechanism. It may be evaluated as one optional feature among several if the dataset supports it; it will not be marketed as the differentiator.

---

## 4. Phased Scope

### Phase 0 — Local core pipeline (target: end of week 3)

**What ships:** A complete, runnable pipeline operating entirely on a static exported subset of the Boss of the SOC (BOTS) dataset. No Splunk dependency.

Functional requirements:
- FR0.1: `LocalFileDataSource` implementing the data-source interface (see §6.2), reading BOTS exports (JSON/CSV).
- FR0.2: Event normalizer converting raw BOTS fields into a common internal `Event` schema: `{timestamp, entity_id, event_type, severity, source, raw_fields}`.
- FR0.3: Correlation engine grouping events into incident clusters by shared entity (user/host/IP) within a configurable sliding time window, using graph-based grouping.
- FR0.4: Feature extraction per incident cluster: event count, event-type diversity, severity sum, entity fan-out, time density, and (optional) performance-deviation feature if present in dataset.
- FR0.5: Scoring model (logistic regression or gradient-boosted trees) trained on BOTS labeled incidents, with held-out evaluation reporting precision, recall, F1, and confusion matrix.
- FR0.6: Dashboard (server-rendered Flask + HTMX, or lightweight React) listing incidents ranked by score, with drill-down to event timeline per incident.
- FR0.7: Sample data bundled in repo so the dashboard runs out-of-the-box with no external dependencies.

**Exit criteria:** Pipeline runs end-to-end on sample data; evaluation report with real precision/recall numbers exists in repo; dashboard displays ranked incidents from local data.

### Phase 1 — Splunk integration (target: end of week 6)

**What ships:** A second data-source implementation connecting to a live Splunk instance, with no changes required to normalizer, correlation engine, scorer, or dashboard.

Functional requirements:
- FR1.1: `SplunkDataSource` implementing the same interface as `LocalFileDataSource`, using Splunk SDK/REST API and/or MCP Server for event retrieval.
- FR1.2: Configuration via `.env` for Splunk host/port/token (HEC token for any data push, search API for pulls).
- FR1.3: Optional performance-metrics ingestion path (Splunk UF + OS metrics add-on) feeding the optional performance-deviation feature from FR0.4 — only if time permits and only evaluated, not assumed valuable.
- FR1.4: Connection health check and graceful fallback: if Splunk is unreachable, the application falls back to `LocalFileDataSource` and surfaces a visible "offline/demo mode" indicator rather than failing.

**Exit criteria:** Same dashboard and scoring pipeline operates against live Splunk data; fallback to local mode verified by killing the Splunk connection mid-session.

### Phase 2 — Investigation agent (target: end of week 7)

**What ships:** A chat-style investigation interface within the dashboard.

Functional requirements:
- FR2.1: Analyst can ask natural-language questions about a selected incident (e.g., "what else did this user do in the last hour?").
- FR2.2: Questions are translated into Splunk searches via Splunk's AI Assistant and/or MCP Server, executed against the active data source, and results summarized in the incident view.
- FR2.3: If MCP Server integration is not stable/documented enough by week 6, fallback is direct SPL generation via Splunk's hosted models or SDK — the feature must degrade gracefully, not block the rest of the demo.

**Exit criteria:** At least one end-to-end natural-language query against a real incident, demoable on video.

### Phase 3 — Polish & submission (weeks 7-8)

- Architecture diagram matching actual built system (not aspirational).
- README, SETUP.md, API docs (OpenAPI/Swagger acceptable).
- Demo video (<3 min, no third-party music/branding).
- Test coverage for correlation engine and scorer specifically.
- License (MIT) and final repo cleanup.

---

## 5. Success Metrics

All metrics must be **measured against the BOTS held-out evaluation set** and reproducible by running a script in the repo. No metric is published without this.

| Metric | How it's measured |
|---|---|
| Precision / Recall / F1 of incident scorer | Held-out split of BOTS labeled incidents |
| Alert-to-incident reduction ratio | (raw event count) ÷ (incident clusters surfaced), on the same dataset |
| Investigation agent success rate | Manual evaluation: % of test questions where the agent returns a relevant, correct answer, out of a fixed test set (e.g., 10-20 questions) |
| Phase 0 standalone runnability | Binary — does `make demo` (or equivalent) run the full pipeline with zero external dependencies |

We will **not** publish: investigation time savings, MTTR improvement, dollar-value breach cost avoidance, or any percentage not derived from the above measurements.

---

## 6. System Design

### 6.1 Architecture overview

Local dataset (BOTS, phase 0) and Splunk instance (HEC + MCP, phase 1) both implement the same data source adapter interface. The adapter feeds an event normalizer, which feeds a correlation engine (entity clustering + scoring), which feeds the incident dashboard. In phase 2, an investigation agent (Splunk AI Assistant + MCP Server) is added alongside the dashboard for natural-language querying of incidents.

*(See architecture diagram delivered earlier in this conversation — `sentinellens_phased_architecture` — for the visual reference. This should be redrawn as a static PNG/SVG for the final submission once Phase 1/2 are actually built, so the diagram matches the real system rather than the plan.)*

### 6.2 Data source interface (critical abstraction)

```python
class DataSource(ABC):
    def get_events(self, query: str, start_time: datetime, end_time: datetime) -> list[Event]:
        ...
    def get_metrics(self, host: str, metric_type: str, timeframe: tuple) -> list[MetricPoint]:
        ...
    def health_check(self) -> bool:
        ...
```

Both `LocalFileDataSource` and `SplunkDataSource` implement this. No component downstream of the adapter may import Splunk-specific or BOTS-specific code directly. This is the boundary that makes Phase 0 a complete, standalone deliverable independent of Phase 1's success.

### 6.3 Technology stack

| Layer | Choice | Rationale |
|---|---|---|
| Backend | Python 3.11, Flask | Team familiarity, fast to build |
| Correlation | networkx | Well-documented graph clustering, no exotic deps |
| ML | scikit-learn | Logistic regression / gradient boosting, sufficient for tabular features |
| Storage | SQLite (dev), document clearly that this is dev-scope only | Avoids "production-ready" overclaim from original proposal |
| Frontend | HTMX + Flask templates (or lightweight React if frontend dev capacity allows) | Reduces frontend build time vs. full React+WebSocket |
| Splunk integration | Splunk Python SDK, REST API, HEC, MCP Server | Required by hackathon; MCP Server targeted for bounty |
| Dataset | Boss of the SOC (BOTS), public Splunk dataset | Provides labeled ground truth |

---

## 7. Security Considerations (for the tool itself)

- Splunk credentials and any API tokens stored via environment variables, never committed to the repo. `.env.example` provided with placeholder values only.
- Dashboard requires basic authentication even in demo mode — do not ship an unauthenticated web UI with read access to security data, even for a hackathon demo.
- Scoring thresholds and correlation logic are open source by requirement (MIT license) — do not present this as a "secret sauce" defense; document it as transparent/auditable by design instead.
- No automated response/remediation actions (per NG1) — this removes an entire class of "agent takes destructive action on bad input" risk from scope.

---

## 8. Risks and Assumptions

| Risk | Likelihood | Mitigation |
|---|---|---|
| BOTS dataset doesn't have a usable entity/temporal structure for clustering | Low-medium | Verify by week 1 — pull a BOTS sample and inspect schema before designing FR0.3 in detail |
| Splunk dev license setup delayed, eating into Phase 1 time | Medium | Apply for dev license in week 1, in parallel with Phase 0 work — independent critical path |
| MCP Server API immature/changes during build | Medium-high | Adapter pattern isolates this; FR2.3 defines explicit fallback |
| Scoring model precision/recall is low (e.g., <60%) on held-out set | Medium | This is acceptable and should be reported honestly — framed as "baseline model, documented limitations" rather than hidden |
| Team underestimates frontend effort | Medium | HTMX-first approach; React only if time allows |
| Performance-metrics feature (FR1.3) adds no signal | Medium-high | Scoped as optional/evaluated, not load-bearing — removing it does not break any other requirement |

---

## 9. Open Questions (resolve before/during week 1)

1. Has anyone on the team pulled and inspected the actual BOTS dataset schema? (Blocks FR0.2/0.3 design.)
2. Who owns the Splunk dev license application — must be submitted week 1 regardless of Phase 0 progress.
3. Frontend: HTMX or React — depends on team's frontend skill distribution, decide before week 3.
4. Is there a team member with prior SOC/security-analyst experience who can validate whether the FR0.3 clustering approach produces sensible incident groupings (sanity check beyond pure metrics)?

---

## 10. Deliverables Checklist (hackathon submission requirements)

- [ ] Public GitHub repo, MIT license
- [ ] README with setup instructions
- [ ] requirements.txt / dependency manifest
- [ ] Architecture diagram (PNG/SVG) matching the built system
- [ ] Sample data for running without Splunk
- [ ] API documentation (OpenAPI/Swagger)
- [ ] Demo video, under 3 minutes, no unlicensed third-party music/branding
- [ ] Evaluation report with measured precision/recall on BOTS held-out set
