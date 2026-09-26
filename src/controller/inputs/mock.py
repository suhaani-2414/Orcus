"""Mock input source for Stage 1 — replays a fixed list of events.

Lets the whole pipeline (event -> decision -> policy -> OS) run and be tested
before any real voice/gesture/keyboard capture exists.
"""

from __future__ import annotations

from collections.abc import Iterator

from controller.decision.schemas import Event
from controller.inputs.base import InputSource


class MockInput(InputSource):
    def __init__(self, events: list[Event]):
        self._events = events

    def events(self) -> Iterator[Event]:
        yield from self._events
