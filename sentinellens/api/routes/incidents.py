# SPDX-License-Identifier: MIT
import json
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, abort
from sentinellens.api.auth import require_auth
from sentinellens.db.repository import Repository

incidents_bp = Blueprint("incidents", __name__)


@incidents_bp.route("/api/v1/incidents")
@require_auth
def list_incidents():
    page      = int(request.args.get("page", 1))
    limit     = min(int(request.args.get("limit", 20)), 100)
    min_score = float(request.args.get("min_score", 0.0))
    band      = request.args.get("band")

    repo = Repository()
    rows, total = repo.get_incidents(page=page, limit=limit, min_score=min_score, band=band)

    # Parse JSON fields
    for r in rows:
        if isinstance(r.get("entities"), str):
            r["entities"] = json.loads(r["entities"])

    from sentinellens.datasource.factory import get_datasource
    ds = get_datasource()

    return jsonify({
        "data": rows,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit,
        },
        "datasource_mode": ds.source_name(),
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    })


@incidents_bp.route("/api/v1/incidents/<incident_id>")
@require_auth
def get_incident(incident_id: str):
    repo = Repository()
    row = repo.get_incident_by_id(incident_id)
    if not row:
        abort(404, description=f"Incident {incident_id} not found")

    # Parse JSON blobs
    for key in ("entities", "features"):
        if isinstance(row.get(key), str):
            row[key] = json.loads(row[key])

    return jsonify(row)


@incidents_bp.route("/api/v1/incidents/<incident_id>/timeline")
@require_auth
def get_timeline(incident_id: str):
    repo = Repository()
    events = repo.get_timeline(incident_id)
    if not events:
        # Verify incident exists
        if not repo.get_incident_by_id(incident_id):
            abort(404, description=f"Incident {incident_id} not found")

    for e in events:
        if isinstance(e.get("raw_fields"), str):
            e["raw_fields"] = json.loads(e["raw_fields"])
        if isinstance(e.get("tags"), str):
            e["tags"] = json.loads(e["tags"])

    return jsonify({"incident_id": incident_id, "events": events, "count": len(events)})


@incidents_bp.route("/api/v1/incidents/<incident_id>/features")
@require_auth
def get_features(incident_id: str):
    repo = Repository()
    features = repo.get_incident_features(incident_id)
    if features is None:
        abort(404, description=f"Incident {incident_id} not found")
    return jsonify({"incident_id": incident_id, "features": features})


@incidents_bp.route("/api/v1/model/report")
@require_auth
def model_report():
    repo = Repository()
    model = repo.get_active_model()
    if not model:
        return jsonify({"error": "No trained model found. Run: python eval/train.py"}), 503
    if isinstance(model.get("feature_set"), str):
        model["feature_set"] = json.loads(model["feature_set"])
    if isinstance(model.get("confusion_matrix"), str):
        model["confusion_matrix"] = json.loads(model["confusion_matrix"])
    return jsonify(model)
