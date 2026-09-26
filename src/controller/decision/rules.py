"""Rule-based decision engine — the Stage 1 stand-in for Laya.

Deterministic and offline: gestures and keys map through config; voice maps
through keyword matching. No model, so it never hallucinates an action and
never stalls on stage. Laya can replace this later behind DecisionEngine.
"""

from __future__ import annotations

import re

from controller.actions.registry import get_action
from controller.decision.base import DecisionEngine
from controller.decision.params import extract_app, extract_workspace
from controller.decision.schemas import (
    Event,
    GestureEvent,
    Intent,
    KeyboardEvent,
    VoiceEvent,
)


class RuleBasedEngine(DecisionEngine):
    def __init__(self, gesture_map: dict[str, str], keyboard_map: dict[str, str]):
        # name/key -> action, sourced from config.
        self.gesture_map = gesture_map
        self.keyboard_map = keyboard_map

    def decide(self, event: Event) -> Intent | None:
        if isinstance(event, GestureEvent):
            return self._from_gesture(event)
        if isinstance(event, KeyboardEvent):
            return self._from_keyboard(event)
        if isinstance(event, VoiceEvent):
            return self._from_voice(event)
        return None

    def _from_gesture(self, event: GestureEvent) -> Intent | None:
        action = self.gesture_map.get(event.name)
        if action is None:
            return None
        # A gesture carries its own recognition confidence.
        return Intent(action=action, confidence=event.confidence)

    def _from_keyboard(self, event: KeyboardEvent) -> Intent | None:
        action = self.keyboard_map.get(event.key)
        if action is None:
            return None
        # Explicit key presses are unambiguous.
        return Intent(action=action, confidence=1.0)

    def _from_voice(self, event: VoiceEvent) -> Intent | None:
        text = event.text.lower().strip()

        if "workspace" in text:
            ws = extract_workspace(text)
            if ws is not None:
                return Intent(
                    action="switch_workspace",
                    parameters={"workspace": ws},
                    confidence=0.95,
                )

        if re.search(r"\b(open|launch|start)\b", text):
            app = extract_app(text)
            if app:
                return Intent(
                    action="open_app",
                    parameters={"application": app},
                    confidence=0.9,
                )

        # Simple keyword -> action table for the rest.
        keyword_actions = [
            (r"\b(volume up|louder|turn it up)\b", "volume_up"),
            (r"\b(volume down|quieter|turn it down)\b", "volume_down"),
            (r"\b(mute|unmute)\b", "mute"),
            (r"\b(play|pause|play pause)\b", "play_pause"),
            (r"\b(next track|next song|skip)\b", "next_track"),
            (r"\b(previous track|previous song|go back)\b", "previous_track"),
            (r"\b(next workspace)\b", "next_workspace"),
            (r"\b(previous workspace)\b", "previous_workspace"),
            (r"\b(lock screen|lock the screen|lock)\b", "lock_screen"),
        ]
        for pattern, action in keyword_actions:
            if re.search(pattern, text) and get_action(action):
                return Intent(action=action, confidence=0.9)

        return None
