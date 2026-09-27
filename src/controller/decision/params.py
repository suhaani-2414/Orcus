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


# Spoken names -> launchable app. Extend as needed / move to config later.
_APP_ALIASES = {
    "browser": "firefox",
    "web browser": "firefox",
    "file manager": "nautilus",
    "files": "nautilus",
    "terminal": "kitty",
    "music": "spotify",
    "music player": "spotify",
    "editor": "code",
    "code editor": "code",
}
_APP_STOPWORDS = {
    "open", "launch", "start", "run", "fire", "up", "bring", "get", "going",
    "please", "can", "you", "my", "the", "a", "an", "some", "for", "me",
}


def extract_app(text: str) -> str | None:
    # Conversational speech rambles ("open my browser. like, it's not…"), so keep
    # only the first clause, then drop filler words and take the app name.
    clause = re.split(r"[.,;:!?]", text.lower())[0]
    words = [w for w in re.findall(r"[a-z0-9+-]+", clause) if w not in _APP_STOPWORDS]
    if not words:
        return None
    name = " ".join(words[:2])
    if name in _APP_ALIASES:
        return _APP_ALIASES[name]
    # Fall back to the first content word (handles "firefox now" -> "firefox").
    return _APP_ALIASES.get(words[0], words[0])


def extract_parameters(action: str, text: str) -> dict:
    """Best-effort parameters for `action` given the raw utterance."""
    text = text.lower().strip()
    if action == "switch_workspace":
        ws = extract_workspace(text)
        return {"workspace": ws} if ws is not None else {}
    if action == "open_app":
        app = extract_app(text)
        return {"application": app} if app else {}
    if action == "move_window":
        for d in ("left", "right", "up", "down"):
            if d in text:
                return {"direction": d}
        return {}  # model default (right)
    if action == "resize_window":
        if any(w in text for w in ("smaller", "shrink", "reduce", "narrower")):
            return {"mode": "shrink"}
        if any(w in text for w in ("bigger", "larger", "grow", "expand", "wider")):
            return {"mode": "grow"}
        return {}  # model default (grow)
    return {}
