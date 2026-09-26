"""Composite decision engine: try engines in order, first intent wins.

Lets us route by modality without any engine knowing about the others:
    CompositeEngine([LayaDecisionEngine(...), RuleBasedEngine(...)])
Laya handles voice; it returns None for gesture/keyboard, so those fall through
to the rule engine. If Laya declines a voice utterance, the rule engine still
gets a chance — a graceful, offline-capable fallback.
"""

from __future__ import annotations

from controller.decision.base import DecisionEngine
from controller.decision.schemas import Event, Intent


class CompositeEngine(DecisionEngine):
    def __init__(self, engines: list[DecisionEngine]):
        self.engines = engines

    def decide(self, event: Event) -> Intent | None:
        for engine in self.engines:
            intent = engine.decide(event)
            if intent is not None:
                return intent
        return None
