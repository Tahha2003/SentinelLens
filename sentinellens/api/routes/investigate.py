# SPDX-License-Identifier: MIT
"""
Investigation agent routes — Phase 2.
Provides a stub that returns a local_mock response in Phase 0.
"""
import uuid
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, abort
from sentinellens.api.auth import require_auth
from sentinellens.db.repository import Repository

investigate_bp = Blueprint("investigate", __name__)


@investigate_bp.route("/api/v1/investigate", methods=["POST"])
@require_auth
def start_investigation():
    data = request.get_json(silent=True) or {}
    incident_id = data.get("incident_id", "").strip()
    query = data.get("query", "").strip()

    if not incident_id or not query:
        return jsonify({"error": "incident_id and query are required"}), 400

    repo = Repository()
    if not repo.get_incident_by_id(incident_id):
        abort(404, description=f"Incident {incident_id} not found")

    session_id = str(uuid.uuid4())
    repo.save_investigation(session_id, incident_id, query)

    # Run investigation in background thread
    import threading
    thread = threading.Thread(
        target=_run_investigation,
        args=(session_id, incident_id, query),
        daemon=True,
    )
    thread.start()

    return jsonify({"session_id": session_id, "status": "queued"}), 202


@investigate_bp.route("/api/v1/investigate/<session_id>")
@require_auth
def get_investigation(session_id: str):
    repo = Repository()
    session = repo.get_investigation(session_id)
    if not session:
        abort(404, description=f"Investigation session {session_id} not found")
    return jsonify(session)


def _run_investigation(session_id: str, incident_id: str, query: str) -> None:
    repo = Repository()
    repo.update_investigation(session_id, status="running")

    try:
        from sentinellens import config

        # Try MCP agent first, fall back to SDK agent, then local mock
        agent_backend = "local_mock"
        spl = None
        summary = ""

        if config.SPLUNK_MCP_URL:
            try:
                from sentinellens.agent.mcp_agent import MCPServerAgent
                agent = MCPServerAgent(config.SPLUNK_MCP_URL, config.SPLUNK_TOKEN)
                incident = _load_incident(repo, incident_id)
                result = agent.query(incident, query)
                spl = result.spl_generated
                summary = result.result_summary
                agent_backend = "mcp_server"
            except Exception:
                pass  # Fall through to mock

        if not summary:
            # Local mock — generate a plausible SPL and summary without Splunk
            spl = _generate_mock_spl(query, incident_id)
            summary = _generate_mock_summary(query, incident_id, repo)
            agent_backend = "local_mock"

        repo.update_investigation(
            session_id,
            status="complete",
            spl_generated=spl,
            result_summary=summary,
            agent_backend=agent_backend,
            completed_at=datetime.now(tz=timezone.utc).isoformat(),
        )

    except Exception as exc:
        repo.update_investigation(
            session_id,
            status="failed",
            error_message=str(exc),
            completed_at=datetime.now(tz=timezone.utc).isoformat(),
        )


def _load_incident(repo, incident_id):
    """Reconstruct a minimal ScoredIncident for the agent."""
    row = repo.get_incident_by_id(incident_id)
    if not row:
        raise ValueError(f"Incident {incident_id} not found")
    # Return a simple namespace object the agent can work with
    import types
    inc = types.SimpleNamespace()
    inc.incident_id = incident_id
    import json
    entities = row.get("entities")
    if isinstance(entities, str):
        entities = json.loads(entities)
    inc.cluster = types.SimpleNamespace()
    inc.cluster.entities = set(entities or [])
    inc.cluster.time_start = row.get("time_start")
    inc.cluster.time_end = row.get("time_end")
    inc.cluster.events = []
    return inc


def _generate_mock_spl(query: str, incident_id: str) -> str:
    q_lower = query.lower()
    repo = Repository()
    incident = repo.get_incident_by_id(incident_id)
    import json
    entities = []
    if incident:
        ents = incident.get("entities", "[]")
        if isinstance(ents, str):
            ents = json.loads(ents)
        entities = ents[:3]
    time_start = incident.get("time_start", "0") if incident else "0"
    time_end = incident.get("time_end", "now") if incident else "now"

    # Build entity filter
    entity_filter = ""
    if entities:
        hosts = [e.replace("host:", "") for e in entities if e.startswith("host:")]
        ips = [e.replace("ip:", "") for e in entities if e.startswith("ip:")]
        users = [e.replace("user:", "") for e in entities if e.startswith("user:")]
        if hosts:
            entity_filter = f'host="{hosts[0]}"'
        elif ips:
            entity_filter = f'(src_ip="{ips[0]}" OR dest_ip="{ips[0]}")'
        elif users:
            entity_filter = f'user="{users[0]}"'

    if "failed" in q_lower or "brute" in q_lower or "login" in q_lower:
        return f'index=botsv3 {entity_filter} sourcetype=wineventlog EventCode=4625 earliest="{time_start}" latest="{time_end}" | stats count by src_ip, user | sort -count'
    if "dns" in q_lower:
        return f'index=botsv3 {entity_filter} sourcetype="stream:dns" earliest="{time_start}" latest="{time_end}" | eval len=len(query) | where len > 40 | table _time, src_ip, query'
    if "network" in q_lower or "connection" in q_lower or "traffic" in q_lower:
        return f'index=botsv3 {entity_filter} earliest="{time_start}" latest="{time_end}" | stats count by sourcetype, src_ip, dest_ip | sort -count'
    if "malware" in q_lower or "virus" in q_lower or "threat" in q_lower:
        return f'index=botsv3 {entity_filter} sourcetype="symantec:ep:risk:file" earliest="{time_start}" latest="{time_end}" | table _time, host, threat_name, file_path, action_taken'
    if "user" in q_lower or "account" in q_lower:
        return f'index=botsv3 {entity_filter} sourcetype=wineventlog earliest="{time_start}" latest="{time_end}" | stats count by user, EventCode | sort -count'
    # Default: all activity for this entity
    return f'index=botsv3 {entity_filter} earliest="{time_start}" latest="{time_end}" | stats count by sourcetype | sort -count'


def _generate_mock_summary(query: str, incident_id: str, repo) -> str:
    incident = repo.get_incident_by_id(incident_id)
    if not incident:
        return "No results found for this incident."

    import json
    entities = incident.get("entities", "[]")
    if isinstance(entities, str):
        entities = json.loads(entities)

    return (
        f"Investigation query: '{query}'\n\n"
        f"This incident involves {len(entities)} entities: {', '.join(list(entities)[:5])}.\n"
        f"Time range: {incident.get('time_start')} to {incident.get('time_end')}.\n\n"
        f"Note: This is a local mock response. Connect Splunk (SPLUNK_HOST, SPLUNK_TOKEN) "
        f"and set SPLUNK_MCP_URL for live investigation results."
    )
