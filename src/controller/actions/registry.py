"""The finite action vocabulary.

This is the security boundary the OUTLINE demands: the decision layer may only
choose an action that exists here, and its parameters are validated against a
strict Pydantic model. There is deliberately no "run_shell_command" action.

Each ActionSpec declares its parameter model, minimum confidence, which
platforms support it, and whether it is destructive (needs confirmation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

# Platform identifiers used throughout the codebase.
LINUX = "linux"
MACOS = "macos"
ALL_PLATFORMS = frozenset({LINUX, MACOS})


class ActionParams(BaseModel):
    """Base for all parameter models. `extra="forbid"` rejects stray keys, so a
    malformed intent fails validation instead of silently passing junk to the OS."""

    model_config = ConfigDict(extra="forbid")


class NoParams(ActionParams):
    pass


class OpenAppParams(ActionParams):
    application: str = Field(min_length=1)


class SwitchWorkspaceParams(ActionParams):
    workspace: int = Field(ge=1, le=99)


class VolumeParams(ActionParams):
    amount: int = Field(default=5, ge=1, le=100)


class MoveWindowParams(ActionParams):
    direction: str = Field(default="right", pattern="^(left|right|up|down)$")


class ResizeWindowParams(ActionParams):
    mode: str = Field(default="grow", pattern="^(grow|shrink)$")


@dataclass(frozen=True)
class ActionSpec:
    name: str
    description: str
    param_model: type[ActionParams] = NoParams
    # Fine-tuned Laya abstains ("none") on unrelated speech, so that — not this
    # threshold — is the main garbage filter. Set strict: only high-confidence
    # commands execute. Some conversational phrasings (~0.57) get denied until
    # the model is retrained with more varied examples.
    min_confidence: float = 0.65
    supported_platforms: frozenset[str] = ALL_PLATFORMS
    destructive: bool = False


def _spec(name: str, desc: str, **kw) -> ActionSpec:
    return ActionSpec(name=name, description=desc, **kw)


# The registry. Adding an action here makes it available to the whole system;
# the OS adapters are responsible for implementing it (or reporting unsupported).
REGISTRY: dict[str, ActionSpec] = {
    a.name: a
    for a in [
        _spec("open_app", "Launch an application", param_model=OpenAppParams),
        _spec("close_app", "Close the focused application"),
        _spec("focus_window", "Focus a window"),
        _spec("move_window", "Move the focused window", param_model=MoveWindowParams),
        _spec("resize_window", "Resize the focused window", param_model=ResizeWindowParams),
        _spec("switch_workspace", "Switch to a workspace by number",
              param_model=SwitchWorkspaceParams),
        _spec("next_workspace", "Switch to the next workspace"),
        _spec("previous_workspace", "Switch to the previous workspace"),
        _spec("play_pause", "Toggle media playback"),
        _spec("next_track", "Skip to the next track"),
        _spec("previous_track", "Go to the previous track"),
        _spec("volume_up", "Raise the volume", param_model=VolumeParams),
        _spec("volume_down", "Lower the volume", param_model=VolumeParams),
        _spec("mute", "Toggle mute"),
        _spec("lock_screen", "Lock the screen", destructive=True),
    ]
}


def get_action(name: str) -> ActionSpec | None:
    return REGISTRY.get(name)
