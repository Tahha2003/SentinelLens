# SPDX-License-Identifier: MIT
"""
Flask application factory for SentinelLens.
"""

from __future__ import annotations

from flask import Flask, redirect, url_for

from sentinellens import config


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="../../templates",
        static_folder="../../sentinellens/static",
    )
    app.secret_key = config.FLASK_SECRET_KEY

    # ── Register API blueprints ────────────────────────────────────────────────
    from sentinellens.api.routes.health     import health_bp
    from sentinellens.api.routes.incidents  import incidents_bp
    from sentinellens.api.routes.pipeline   import pipeline_bp
    from sentinellens.api.routes.investigate import investigate_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(incidents_bp)
    app.register_blueprint(pipeline_bp)
    app.register_blueprint(investigate_bp)

    # ── Dashboard routes ───────────────────────────────────────────────────────
    from sentinellens.api.auth import require_auth

    @app.route("/")
    def index():
        return redirect(url_for("dashboard"))

    @app.route("/dashboard")
    @require_auth
    def dashboard():
        from flask import render_template
        from sentinellens.db.repository import Repository
        from sentinellens.datasource.factory import get_datasource

        repo = Repository()
        rows, total = repo.get_incidents(page=1, limit=20)

        import json
        for r in rows:
            if isinstance(r.get("entities"), str):
                r["entities"] = json.loads(r["entities"])

        ds = get_datasource()
        recent_runs = repo.get_recent_runs(limit=5)

        return render_template(
            "incidents.html",
            incidents=rows,
            total=total,
            datasource_mode=ds.source_name(),
            recent_runs=recent_runs,
        )

    @app.route("/incidents/<incident_id>")
    @require_auth
    def incident_detail(incident_id: str):
        from flask import render_template, abort
        from sentinellens.db.repository import Repository

        import json
        repo = Repository()
        row = repo.get_incident_by_id(incident_id)
        if not row:
            abort(404)

        for key in ("entities", "features"):
            if isinstance(row.get(key), str):
                row[key] = json.loads(row[key])

        events = repo.get_timeline(incident_id)
        for e in events:
            if isinstance(e.get("raw_fields"), str):
                e["raw_fields"] = json.loads(e["raw_fields"])
            if isinstance(e.get("tags"), str):
                e["tags"] = json.loads(e["tags"])

        return render_template(
            "incident_detail.html",
            incident=row,
            events=events,
            dashboard_user=config.DASHBOARD_USER,
            dashboard_password=config.DASHBOARD_PASSWORD,
        )

    # ── Error handlers ─────────────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        from flask import jsonify, request
        if request.path.startswith("/api/"):
            return jsonify({"error": str(e)}), 404
        return f"<h1>404 — Not Found</h1><p>{e}</p>", 404

    @app.errorhandler(500)
    def server_error(e):
        from flask import jsonify, request
        if request.path.startswith("/api/"):
            return jsonify({"error": "Internal server error"}), 500
        return f"<h1>500 — Server Error</h1><p>{e}</p>", 500

    return app


# Allow `flask --app sentinellens.api.app run`
app = create_app()
