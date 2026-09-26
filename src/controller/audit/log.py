"""Structured audit logging.

Every decision+execution produces one JSON record, matching the OUTLINE's audit
spec. Records go to a JSONL file and/or stdout. Named 'audit' (not 'logging') to
avoid shadowing the stdlib module.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO


class AuditLog:
    def __init__(self, path: str | Path | None = None, stream: TextIO | None = sys.stdout):
        self.path = Path(path) if path else None
        self.stream = stream

    def record(
        self,
        *,
        platform: str,
        input_type: str,
        raw_input: Any,
        decision: str | None,
        parameters: dict,
        confidence: float | None,
        policy: str,
        execution: str,
    ) -> dict:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform": platform,
            "input_type": input_type,
            "raw_input": raw_input,
            "decision": decision,
            "parameters": parameters,
            "confidence": confidence,
            "policy": policy,
            "execution": execution,
        }
        line = json.dumps(entry)
        if self.path:
            with self.path.open("a") as f:
                f.write(line + "\n")
        if self.stream:
            self.stream.write(line + "\n")
        return entry
