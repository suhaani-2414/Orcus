"""Shared data contracts: normalized input events and structured intents.

These are the spine of the system. Every input source produces an Event; the
decision layer turns an Event into an Intent; the policy layer validates the
Intent; the OS adapter executes it. Nothing here knows about any OS.
"""

from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field
from typing_extensions import Annotated


# --- Input events ----------------------------------------------------------
# Each input modality normalizes to one of these. Downstream code depends only
# on the shape here, never on where the event came from.


class VoiceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["voice"] = "voice"
    text: str


class GestureEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["gesture"] = "gesture"
    name: str
    confidence: float = Field(ge=0.0, le=1.0)


class KeyboardEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["keyboard"] = "keyboard"
    key: str


# Discriminated union so parsing dispatches on the "type" field.
Event = Annotated[
    Union[VoiceEvent, GestureEvent, KeyboardEvent],
    Field(discriminator="type"),
]


# --- Intent ----------------------------------------------------------------
# The single structured command the rest of the system acts on. Laya (or any
# DecisionEngine) produces this; it never produces shell commands.


class Intent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
