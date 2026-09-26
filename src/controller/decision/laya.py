"""Laya decision engine — voice intent classification.

Laya (convaiinnovations/laya) is a non-autoregressive System-1 model: given a
state and typed questions it returns typed answers with calibrated probabilities
in one forward pass, and never generates free text. That makes it a natural
Decision-layer engine:

  * We ask one `choice` question whose options ARE the action registry, so Laya
    can only ever pick an action that exists — the vocabulary is enforced by the
    model's shape, not by parsing.
  * Its calibrated `confidence` becomes the Intent confidence the policy layer
    already gates on.
  * A synthetic "none" option lets Laya reject unrelated speech instead of being
    forced into a nearest match.

Laya classifies the action; parameters (workspace number, app name) come from
controller.decision.params. Gesture/keyboard events are already discrete labels,
so this engine ignores them (return None) and leaves them to the rule engine.
"""

from __future__ import annotations

from typing import Protocol

from controller.actions.registry import REGISTRY
from controller.decision.base import DecisionEngine
from controller.decision.params import extract_parameters
from controller.decision.schemas import Event, Intent, VoiceEvent

# Option key Laya can pick to say "no action matches".
NONE_OPTION = "none"
_NONE_CRITERIA = "the request does not match any available action, or is unrelated"


class LayaClient(Protocol):
    """Anything exposing Laya's inference call. The downloaded repo's RLAgent
    (rl_agent_api.py) and the `laya` package both satisfy this shape."""

    def system_one(self, state: str, questions: dict) -> dict: ...


# Question id used everywhere so training and inference build the identical
# choice question (same options, same order -> aligned option markers).
QUESTION_ID = "action"
_INSTRUCTIONS = (
    "Which action does the user want to perform? "
    "Pick the closest match, or 'none' if nothing fits."
)


def build_action_question(actions: list[str], allow_none: bool = True) -> dict:
    """The single choice question over the action registry (+ optional 'none').
    Shared by LayaDecisionEngine and the fine-tuning script so option text and
    order match exactly."""
    criteria = {name: REGISTRY[name].description for name in actions}
    if allow_none:
        criteria[NONE_OPTION] = _NONE_CRITERIA
    return {
        QUESTION_ID: {
            "type": "choice",
            "instructions": _INSTRUCTIONS,
            "criteria": criteria,
        }
    }


class LayaDecisionEngine(DecisionEngine):
    QUESTION_ID = "action"

    def __init__(
        self,
        client: LayaClient,
        actions: list[str] | None = None,
        allow_none: bool = True,
    ):
        self.client = client
        # Which actions Laya may choose among (defaults to the whole registry).
        self.actions = actions or list(REGISTRY.keys())
        # Offer a synthetic "none" option. The zero-shot base checkpoint over-
        # picks it, so callers relying on the base model may disable it and gate
        # on confidence via the policy layer instead.
        self.allow_none = allow_none

    def _question(self) -> dict:
        criteria = {name: REGISTRY[name].description for name in self.actions}
        if self.allow_none:
            criteria[NONE_OPTION] = _NONE_CRITERIA
        return {
            self.QUESTION_ID: {
                "type": "choice",
                "instructions": "Which action does the user want to perform? "
                "Pick the closest match, or 'none' if nothing fits.",
                "criteria": criteria,
            }
        }

    def decide(self, event: Event) -> Intent | None:
        # Laya is for natural language; discrete inputs go through the rule engine.
        if not isinstance(event, VoiceEvent):
            return None

        result = self.client.system_one(event.text, self._question())
        answer = result["answers"][self.QUESTION_ID]
        action = answer["choice"]
        if action == NONE_OPTION:
            return None

        confidence = float(answer.get("confidence", 0.0))
        parameters = extract_parameters(action, event.text)
        return Intent(action=action, parameters=parameters, confidence=confidence)
