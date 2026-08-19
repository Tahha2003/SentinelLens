# SPDX-License-Identifier: MIT
"""InvestigationAgent abstract base class — Phase 2."""

from __future__ import annotations

from abc import ABC, abstractmethod

from sentinellens.models import InvestigationResult


class InvestigationAgent(ABC):

    @abstractmethod
    def query(self, incident, question: str) -> InvestigationResult:
        """
        Translate a natural-language question into a Splunk search,
        execute it, and summarize the results.
        """
        ...
