# SPDX-License-Identifier: MIT
"""
SentinelLens configuration loader.

Reads from environment variables (populated by .env via python-dotenv).
Raises a clear error at startup if any required variable is missing.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env file if present (no-op in production where env vars are injected)
load_dotenv(override=False)


def _require(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        raise RuntimeError(
            f"Required environment variable '{key}' is not set. "
            f"Copy .env.example to .env and fill in the values."
        )
    return val


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _int(key: str, default: int) -> int:
    val = os.getenv(key, str(default)).strip()
    try:
        return int(val)
    except ValueError:
        raise RuntimeError(f"Environment variable '{key}' must be an integer, got '{val}'")


# ── Auth ───────────────────────────────────────────────────────────────────────
DASHBOARD_USER: str = _optional("DASHBOARD_USER", "admin")
DASHBOARD_PASSWORD: str = _optional("DASHBOARD_PASSWORD", "changeme")

# ── Flask ──────────────────────────────────────────────────────────────────────
FLASK_SECRET_KEY: str = _optional("FLASK_SECRET_KEY", "dev-secret-not-for-production")
FLASK_ENV: str = _optional("FLASK_ENV", "development")

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_LEVEL: str = _optional("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# ── Data Paths ─────────────────────────────────────────────────────────────────
BOTS_DATA_PATH: str = _optional("BOTS_DATA_PATH", "data/bots_sample_events.json")
MODEL_PATH: str = _optional("MODEL_PATH", "models/scorer_v1.joblib")

# ── Correlation ────────────────────────────────────────────────────────────────
CORRELATION_WINDOW_MINUTES: int = _int("CORRELATION_WINDOW_MINUTES", 15)
MIN_CLUSTER_SIZE: int = _int("MIN_CLUSTER_SIZE", 2)

# ── Splunk (Phase 1) ───────────────────────────────────────────────────────────
SPLUNK_HOST: str = _optional("SPLUNK_HOST", "")
SPLUNK_PORT: int = _int("SPLUNK_PORT", 8089)
SPLUNK_TOKEN: str = _optional("SPLUNK_TOKEN", "")

# ── Investigation Agent (Phase 2) ─────────────────────────────────────────────
SPLUNK_MCP_URL: str = _optional("SPLUNK_MCP_URL", "")

# ── Derived ────────────────────────────────────────────────────────────────────
IS_LOCAL_MODE: bool = not bool(SPLUNK_HOST and SPLUNK_TOKEN)
