"""Policy / safety layer.

Never execute a decision directly. Every intent passes through here first:
  1. the action must exist in the registry
  2. its parameters must validate against the action's strict model
  3. confidence must meet the action's threshold
  4. the action must be supported on the current platform
  5. destructive actions require confirmation

The result is a PolicyDecision; the caller executes only if `allowed`.
"""

from __future__ import annotations

from typing import Callable

from pydantic import BaseModel, ValidationError

from controller.actions.registry import ActionSpec, get_action
from controller.decision.schemas import Intent

# Called for destructive actions. Returns True to permit. Default denies, so a
# missing confirmation handler fails safe.
ConfirmFn = Callable[[Intent, ActionSpec], bool]


def _deny(_intent: Intent, _spec: ActionSpec) -> bool:
    return False


class PolicyDecision(BaseModel):
    allowed: bool
    reason: str
    requires_confirmation: bool = False
    # Parameters re-validated/normalized by the action's model, when allowed.
    normalized_parameters: dict = {}


class PolicyEngine:
    def __init__(
        self,
        platform: str,
        confirm: ConfirmFn | None = None,
        min_confidence: float | None = None,
    ):
        self.platform = platform
        self.confirm = confirm or _deny
        # Global confidence threshold from config; overrides each action's
        # registry default when set. None -> fall back to the per-action value.
        self.min_confidence = min_confidence

    def evaluate(self, intent: Intent) -> PolicyDecision:
        spec = get_action(intent.action)
        if spec is None:
            return PolicyDecision(allowed=False, reason=f"unknown action: {intent.action}")

        try:
            params = spec.param_model(**intent.parameters)
        except ValidationError as e:
            return PolicyDecision(allowed=False, reason=f"invalid parameters: {e.errors()}")

        threshold = spec.min_confidence if self.min_confidence is None else self.min_confidence
        if intent.confidence < threshold:
            return PolicyDecision(
                allowed=False,
                reason=f"confidence {intent.confidence:.2f} below threshold {threshold:.2f}",
            )

        if self.platform not in spec.supported_platforms:
            return PolicyDecision(
                allowed=False,
                reason=f"action '{intent.action}' unsupported on {self.platform}",
            )

        if spec.destructive and not self.confirm(intent, spec):
            return PolicyDecision(
                allowed=False,
                reason=f"destructive action '{intent.action}' requires confirmation (not confirmed)",
                requires_confirmation=True,
                normalized_parameters=params.model_dump(),
            )

        return PolicyDecision(
            allowed=True, reason="allowed", normalized_parameters=params.model_dump()
        )
