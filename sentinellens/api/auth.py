# SPDX-License-Identifier: MIT
"""HTTP Basic Auth middleware for all routes."""

from functools import wraps

from flask import request, Response

from sentinellens import config


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if (
            not auth
            or auth.username != config.DASHBOARD_USER
            or auth.password != config.DASHBOARD_PASSWORD
        ):
            return Response(
                "Authentication required.",
                401,
                {"WWW-Authenticate": 'Basic realm="SentinelLens"'},
            )
        return f(*args, **kwargs)
    return decorated
