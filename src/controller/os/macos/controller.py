"""macOS OS adapter — stubbed for now.

The interface exists so the factory and the rest of the system treat macOS as a
first-class platform. Real execution (Accessibility API, AppleScript, Shortcuts)
is deferred; until then every action reports "unsupported" rather than failing
unpredictably. This is the "drop-in adapter" the architecture promises.
"""

from __future__ import annotations

from controller.actions.registry import MACOS
from controller.decision.schemas import Intent
from controller.os.base import ExecutionResult, OSController


class MacOSController(OSController):
    platform = MACOS

    def execute(self, intent: Intent) -> ExecutionResult:
        return ExecutionResult(
            status="unsupported",
            detail="macOS adapter not yet implemented",
        )
