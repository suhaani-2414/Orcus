"""The pipeline: event -> decision -> policy -> OS controller, with audit.

This is the platform-independent spine. It wires the replaceable pieces
together and records every step. Nothing here knows which OS is underneath.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter, time
from typing import Callable

from controller.audit.log import AuditLog
from controller.decision.base import DecisionEngine
from controller.decision.schemas import Event
from controller.os.base import ExecutionResult, OSController
from controller.policy.validator import PolicyEngine

# Called after each handled step with the audit entry dict. Lets a UI observe
# the pipeline without the pipeline knowing anything about the UI.
Observer = Callable[[dict], None]


@dataclass
class PendingConfirmation:
    event_type: str
    raw: dict
    intent: object
    created_at: float


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
        self._pending: PendingConfirmation | None = None
        self.confirmation_timeout_seconds = 30.0

    def handle(self, event: Event) -> ExecutionResult:
        started = perf_counter()
        raw = event.model_dump()
        decision_started = perf_counter()
        intent = self.engine.decide(event)
        decision_ms = (perf_counter() - decision_started) * 1000

        if intent is None:
            self._audit(
                event.type, raw, None, {}, None, "no_intent", "skipped",
                {"decision": round(decision_ms, 2), "total": round((perf_counter() - started) * 1000, 2)},
            )
            return ExecutionResult(status="error", detail="no intent produced")

        policy_started = perf_counter()
        source_name = getattr(event, "name", None)
        decision = self.policy.evaluate(intent, source_name=source_name)
        policy_ms = (perf_counter() - policy_started) * 1000
        if decision.requires_confirmation:
            intent.parameters = decision.normalized_parameters
            self._pending = PendingConfirmation(event.type, raw, intent, time())
            self._audit(
                event.type, raw, intent.action, intent.parameters,
                intent.confidence, decision.reason, "pending",
                {"decision": round(decision_ms, 2), "policy": round(policy_ms, 2),
                 "total": round((perf_counter() - started) * 1000, 2)},
            )
            return ExecutionResult(
                status="confirmation_required",
                detail=f"confirm action '{intent.action}' to continue",
            )
        if not decision.allowed:
            self._audit(
                event.type, raw, intent.action, intent.parameters,
                intent.confidence, f"denied: {decision.reason}", "skipped",
                {"decision": round(decision_ms, 2), "policy": round(policy_ms, 2),
                 "total": round((perf_counter() - started) * 1000, 2)},
            )
            return ExecutionResult(status="error", detail=decision.reason)

        # Execute with policy-normalized parameters.
        intent.parameters = decision.normalized_parameters
        execute_started = perf_counter()
        result = self.controller.execute(intent)
        execute_ms = (perf_counter() - execute_started) * 1000
        self._audit(
            event.type, raw, intent.action, intent.parameters,
            intent.confidence, "allowed", result.status,
            {"decision": round(decision_ms, 2), "policy": round(policy_ms, 2),
             "execute": round(execute_ms, 2),
             "total": round((perf_counter() - started) * 1000, 2)},
        )
        return result

    def confirm_pending(self, confirmed: bool) -> ExecutionResult:
        pending = self._pending
        self._pending = None
        if pending is None:
            return ExecutionResult(status="error", detail="no action is awaiting confirmation")
        if time() - pending.created_at > self.confirmation_timeout_seconds:
            self._audit(
                pending.event_type, pending.raw, pending.intent.action,
                pending.intent.parameters, pending.intent.confidence,
                "confirmation expired", "cancelled",
            )
            return ExecutionResult(status="cancelled", detail="confirmation expired")
        if not confirmed:
            self._audit(
                pending.event_type, pending.raw, pending.intent.action,
                pending.intent.parameters, pending.intent.confidence,
                "confirmation cancelled", "cancelled",
            )
            return ExecutionResult(status="cancelled", detail="action cancelled")

        result = self.controller.execute(pending.intent)
        self._audit(
            pending.event_type, pending.raw, pending.intent.action,
            pending.intent.parameters, pending.intent.confidence,
            "confirmed", result.status,
        )
        return result

    @property
    def has_pending_confirmation(self) -> bool:
        return self._pending is not None

    def _audit(self, input_type, raw, decision, params, confidence, policy, execution,
               timings_ms=None):
        entry = self.audit.record(
            platform=self.controller.platform,
            input_type=input_type,
            raw_input=raw,
            decision=decision,
            parameters=params,
            confidence=confidence,
            policy=policy,
            execution=execution,
            timings_ms=timings_ms,
        )
        if self.observer is not None:
            self.observer(entry)
