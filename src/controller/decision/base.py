"""The DecisionEngine interface.

The rest of the app depends on this, never on a concrete engine. Stage 1 ships
a rule-based engine; Laya slots in later behind the same interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from controller.decision.schemas import Event, Intent


class DecisionEngine(ABC):
    @abstractmethod
    def decide(self, event: Event) -> Intent | None:
        """Map a normalized event to a structured intent, or None if unmapped."""
        raise NotImplementedError
