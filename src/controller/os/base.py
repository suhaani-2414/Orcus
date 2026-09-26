"""OS controller interface and execution result.

The only layer allowed to contain OS-specific code lives behind this interface.
Intents in, structured results out. The core never branches on the OS; the
factory picks the right controller once at startup.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel

from controller.decision.schemas import Intent


class ExecutionResult(BaseModel):
    status: Literal["success", "error", "unsupported"]
    detail: str = ""


class OSController(ABC):
    #: Platform id this controller implements ("linux" / "macos").
    platform: str

    @abstractmethod
    def execute(self, intent: Intent) -> ExecutionResult:
        raise NotImplementedError
