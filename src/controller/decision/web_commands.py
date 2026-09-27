"""High-priority engine for open-ended web commands (search, open URL).

Runs BEFORE Laya in the composite: Laya is a fixed 15-action classifier and
can't extract a free-text query, so these parameterized commands are matched by
regex here. Only fires on clear web phrasings; everything else falls through to
Laya. This is the extensibility pattern — a new "skill" = a small engine like
this + a registry action + an adapter handler.
"""

from __future__ import annotations

import re

from controller.decision.base import DecisionEngine
from controller.decision.schemas import Event, Intent, VoiceEvent


class WebCommandEngine(DecisionEngine):
    def decide(self, event: Event) -> Intent | None:
        if not isinstance(event, VoiceEvent):
            return None
        text = event.text.lower().strip().rstrip(".!?")

        # "open/go to/visit <domain>"  (must look like a domain: has a dot)
        m = re.search(r"\b(?:open|go to|visit|launch)\s+(\S+\.\S+)", text)
        if m:
            return Intent(action="open_url", parameters={"url": m.group(1)}, confidence=0.95)

        # "search <query> on youtube/google"
        m = re.search(r"\bsearch\s+(?:for\s+)?(.+?)\s+on\s+(youtube|google)\b", text)
        if m:
            return Intent(
                action="web_search",
                parameters={"query": m.group(1).strip(), "engine": m.group(2)},
                confidence=0.95,
            )

        # "search youtube/google for <query>"  /  "youtube <query>"
        m = re.search(r"\b(?:search\s+)?(youtube|google)\s+(?:for\s+)?(.+)", text)
        if m and m.group(2).strip():
            return Intent(
                action="web_search",
                parameters={"query": m.group(2).strip(), "engine": m.group(1)},
                confidence=0.9,
            )

        # "search [for] <query>"  /  "google <query>"  -> default google.
        # Skip "workspace" so "switch workspace" stays with Laya.
        m = re.search(r"\b(?:search|google)\s+(?:for\s+)?(.+)", text)
        if m and "workspace" not in text and m.group(1).strip():
            return Intent(
                action="web_search",
                parameters={"query": m.group(1).strip(), "engine": "google"},
                confidence=0.9,
            )

        return None
