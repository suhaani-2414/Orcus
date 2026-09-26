"""The pipeline: event -> decision -> policy -> OS controller, with audit.

This is the platform-independent spine. It wires the replaceable pieces
together and records every step. Nothing here knows which OS is underneath.
"""

from __future__ import annotations

from typing import Callable

from controller.audit.log import AuditLog
from controller.decision.base import DecisionEngine
from controller.decision.schemas import Event
from controller.os.base import ExecutionResult, OSController
from controller.policy.validator import PolicyEngine

# Called after each handled step with the audit entry dict. Lets a UI observe
# the pipeline without the pipeline knowing anything about the UI.
Observer = Callable[[dict], None]


class Pipeline:
    def __init__(
        self,
        engine: DecisionEngine,
        policy: PolicyEngine,
        controller: OSController,
        audit: AuditLog,
        observer: Observer | None = None,
    ):
        self.engine = engine
        self.policy = policy
        self.controller = controller
        self.audit = audit
        self.observer = observer

    def handle(self, event: Event) -> ExecutionResult:
        raw = event.model_dump()
        intent = self.engine.decide(event)

        if intent is None:
            self._audit(event.type, raw, None, {}, None, "no_intent", "skipped")
            return ExecutionResult(status="error", detail="no intent produced")

        decision = self.policy.evaluate(intent)
        if not decision.allowed:
            self._audit(
                event.type, raw, intent.action, intent.parameters,
                intent.confidence, f"denied: {decision.reason}", "skipped",
            )
            return ExecutionResult(status="error", detail=decision.reason)

        # Execute with policy-normalized parameters.
        intent.parameters = decision.normalized_parameters
        result = self.controller.execute(intent)
        self._audit(
            event.type, raw, intent.action, intent.parameters,
            intent.confidence, "allowed", result.status,
        )
        return result

    def _audit(self, input_type, raw, decision, params, confidence, policy, execution):
        entry = self.audit.record(
            platform=self.controller.platform,
            input_type=input_type,
            raw_input=raw,
            decision=decision,
            parameters=params,
            confidence=confidence,
            policy=policy,
            execution=execution,
        )
        if self.observer is not None:
            self.observer(entry)
