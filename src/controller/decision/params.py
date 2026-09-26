"""Parameter extraction from voice text.

Laya (and the rule engine) decide *which* action; neither extracts the numbers
and names an action needs. That lives here, shared by both, so there's one place
that knows how to pull a workspace number or an app name out of an utterance.
"""

from __future__ import annotations

import re

_WORD_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def extract_workspace(text: str) -> int | None:
    m = re.search(r"workspace\s+(\d+)", text)
    if m:
        return int(m.group(1))
    m = re.search(r"workspace\s+(\w+)", text)
    if m and m.group(1) in _WORD_NUM:
        return _WORD_NUM[m.group(1)]
    return None


def extract_app(text: str) -> str | None:
    app = re.sub(r"\b(open|launch|start)\b", "", text).strip()
    return app or None


def extract_parameters(action: str, text: str) -> dict:
    """Best-effort parameters for `action` given the raw utterance."""
    text = text.lower().strip()
    if action == "switch_workspace":
        ws = extract_workspace(text)
        return {"workspace": ws} if ws is not None else {}
    if action == "open_app":
        app = extract_app(text)
        return {"application": app} if app else {}
    return {}
