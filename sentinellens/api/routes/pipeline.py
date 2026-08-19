# SPDX-License-Identifier: MIT
from flask import Blueprint, jsonify, abort
from sentinellens.api.auth import require_auth
from sentinellens.db.repository import Repository
from sentinellens.pipeline.runner import PipelineRunner

pipeline_bp = Blueprint("pipeline", __name__)


@pipeline_bp.route("/api/v1/pipeline/run", methods=["POST"])
@require_auth
def run_pipeline():
    # Verify scorer is available before starting
    try:
        from sentinellens.pipeline.runner import get_scorer
        get_scorer()
    except RuntimeError as exc:
        return jsonify({"error": str(exc), "hint": "Run: python eval/train.py"}), 503

    repo = Repository()
    runner = PipelineRunner(repo)
    run_id = runner.run_async()
    return jsonify({"run_id": run_id, "status": "queued"}), 202


@pipeline_bp.route("/api/v1/pipeline/status/<run_id>")
@require_auth
def pipeline_status(run_id: str):
    repo = Repository()
    run = repo.get_pipeline_run(run_id)
    if not run:
        abort(404, description=f"Pipeline run {run_id} not found")
    return jsonify(run)


@pipeline_bp.route("/api/v1/datasource/status")
@require_auth
def datasource_status():
    from sentinellens.datasource.factory import get_datasource
    ds = get_datasource()
    return jsonify({
        "mode": ds.source_name(),
        "healthy": ds.health_check(),
    })
