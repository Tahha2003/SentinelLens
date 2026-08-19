# SPDX-License-Identifier: MIT
from datetime import datetime, timezone
from flask import Blueprint, jsonify
from sentinellens.api.auth import require_auth
from sentinellens.datasource.factory import get_datasource
from sentinellens.db.repository import Repository
from sentinellens import config

health_bp = Blueprint("health", __name__)


@health_bp.route("/api/v1/health")
@require_auth
def health():
    repo = Repository()
    ds = get_datasource()

    # Try to load scorer
    scorer_ok = False
    try:
        from sentinellens.pipeline.runner import get_scorer
        get_scorer()
        scorer_ok = True
    except Exception:
        scorer_ok = False

    active_model = repo.get_active_model()

    return jsonify({
        "status": "ok" if scorer_ok else "degraded",
        "datasource": {
            "mode": ds.source_name(),
            "healthy": ds.health_check(),
        },
        "database": repo.health_check(),
        "scorer_loaded": scorer_ok,
        "active_model": active_model.get("model_id", "")[:12] + "..." if active_model else None,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    })
