# SPDX-License-Identifier: MIT
"""
DataSource factory — single entry point for obtaining the correct DataSource.

All other modules call get_datasource().
Never instantiate LocalFileDataSource or SplunkDataSource directly outside this module.
"""

from __future__ import annotations

import logging

from sentinellens.datasource.base import DataSource

logger = logging.getLogger(__name__)

_instance: DataSource | None = None


def get_datasource() -> DataSource:
    """
    Return the active DataSource instance (singleton).

    Selection logic:
    1. If SPLUNK_HOST and SPLUNK_TOKEN are set → try SplunkDataSource
    2. If Splunk is unreachable or not configured → fall back to LocalFileDataSource
    3. Surface the active mode so callers can show 'OFFLINE MODE' banner
    """
    global _instance
    if _instance is not None:
        return _instance

    from sentinellens import config

    if config.SPLUNK_HOST and config.SPLUNK_TOKEN:
        try:
            from sentinellens.datasource.splunk import SplunkDataSource
            candidate = SplunkDataSource(
                host=config.SPLUNK_HOST,
                port=config.SPLUNK_PORT,
                token=config.SPLUNK_TOKEN,
            )
            if candidate.health_check():
                logger.info("DataSource: Splunk LIVE mode (%s:%d)", config.SPLUNK_HOST, config.SPLUNK_PORT)
                _instance = candidate
                return _instance
            else:
                logger.warning(
                    "Splunk configured but unreachable — falling back to local data"
                )
        except Exception as exc:
            logger.warning("Splunk connection failed (%s) — using local data", exc)

    # Fall back to local
    from sentinellens.datasource.local import LocalFileDataSource
    _instance = LocalFileDataSource(config.BOTS_DATA_PATH)
    logger.info("DataSource: LOCAL mode (%s)", config.BOTS_DATA_PATH)
    return _instance


def reset_datasource() -> None:
    """
    Clear the singleton. Used in tests and health-check recovery.
    Forces re-evaluation on next get_datasource() call.
    """
    global _instance
    _instance = None
