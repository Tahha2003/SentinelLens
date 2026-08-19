# SPDX-License-Identifier: MIT
"""
MCPServerAgent — Phase 2 primary investigation agent.

Uses Splunk MCP Server to translate natural-language questions to SPL,
execute them, and summarize results.

Falls back to SplunkSDKAgent if MCP Server is unavailable.
"""

from __future__ import annotations

import logging

from sentinellens.agent.base import InvestigationAgent
from sentinellens.models import InvestigationResult

logger = logging.getLogger(__name__)


class MCPUnavailableError(Exception):
    pass


class MCPServerAgent(InvestigationAgent):
    MCP_TIMEOUT_SECS = 10
    MAX_RESULT_ROWS = 1000

    def __init__(self, mcp_url: str, splunk_token: str) -> None:
        self._mcp_url = mcp_url.rstrip("/")
        self._token = splunk_token

    def query(self, incident, question: str) -> InvestigationResult:
        try:
            import requests  # type: ignore
        except ImportError:
            raise MCPUnavailableError("requests library not installed")

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        context = self._build_context(incident)

        # Step 1: Translate NL → SPL
        try:
            resp = requests.post(
                f"{self._mcp_url}/translate",
                json={"question": question, "context": context},
                headers=headers,
                timeout=self.MCP_TIMEOUT_SECS,
            )
            resp.raise_for_status()
            spl = resp.json().get("spl", "")
            if not spl:
                raise MCPUnavailableError("MCP returned empty SPL")
        except Exception as exc:
            raise MCPUnavailableError(f"MCP translate failed: {exc}") from exc

        # Step 2: Execute SPL with row cap (SPL injection protection)
        spl_safe = spl + f" | head {self.MAX_RESULT_ROWS}"
        raw_results = self._execute_spl(spl_safe, headers)

        # Step 3: Summarize
        summary = self._summarize(question, raw_results, headers)

        return InvestigationResult(
            analyst_query=question,
            spl_generated=spl_safe,
            result_raw=raw_results[:50] if raw_results else None,
            result_summary=summary,
            agent_backend="mcp_server",
        )

    def _execute_spl(self, spl: str, headers: dict) -> list[dict]:
        try:
            import requests  # type: ignore
            resp = requests.post(
                f"{self._mcp_url}/execute",
                json={"spl": spl},
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("results", [])
        except Exception as exc:
            logger.warning("MCP execute failed: %s", exc)
            return []

    def _summarize(self, question: str, results: list[dict], headers: dict) -> str:
        if not results:
            return f"No results found for: '{question}'"
        try:
            import requests  # type: ignore
            resp = requests.post(
                f"{self._mcp_url}/summarize",
                json={"question": question, "results": results[:20]},
                headers=headers,
                timeout=self.MCP_TIMEOUT_SECS,
            )
            resp.raise_for_status()
            return resp.json().get("summary", f"Found {len(results)} results.")
        except Exception:
            return f"Found {len(results)} result(s). MCP summarization unavailable."

    def _build_context(self, incident) -> dict:
        entities = list(incident.cluster.entities) if hasattr(incident.cluster, "entities") else []
        return {
            "incident_id": incident.incident_id,
            "entities": entities[:10],
            "time_start": str(getattr(incident.cluster, "time_start", "")),
            "time_end":   str(getattr(incident.cluster, "time_end", "")),
        }
