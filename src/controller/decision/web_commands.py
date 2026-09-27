"""High-priority engine for open-ended web commands (navigate, search).

Runs BEFORE Laya. Navigation ("go to youtube") resolves a spoken name to a URL
via the SiteStore; unknown names go to an optional resolver (Gemini) and are
saved for next time. Searches ("search cats", "search cats on youtube") become
web_search. OS phrases ("go to workspace three") are left for Laya.
"""

from __future__ import annotations

import re

from controller.decision.base import DecisionEngine
from controller.decision.schemas import Event, Intent, VoiceEvent

# Explicit navigation verbs (mean "open a website").
_NAV = r"(?:go to|goto|visit|navigate to|pull up|take me to|browse to|browse)"
# Ambiguous verbs — only navigate for a KNOWN site or a domain, else defer to
# Laya (which may launch an app: "open firefox").
_OPEN = r"(?:open|launch|open up)"
_DOMAIN = re.compile(r"^[\w-]+(?:\.[\w-]+)+(?:/\S*)?$")
_OS_WORDS = re.compile(r"\b(workspace|desktop|window|volume|track|screen)\b")


def _normalize_url(url: str) -> str:
    return url if url.startswith(("http://", "https://")) else f"https://{url}"


class WebCommandEngine(DecisionEngine):
    def __init__(self, sites=None, resolver=None):
        # sites: SiteStore; resolver: callable(name)->url|None (e.g. Gemini).
        self.sites = sites
        self.resolver = resolver

    def _resolve(self, target: str, allow_resolver: bool) -> str | None:
        target = target.strip().strip("?.!").strip()
        if not target or _OS_WORDS.search(target):
            return None
        if _DOMAIN.match(target):
            return _normalize_url(target)
        if self.sites is not None:
            url = self.sites.get(target) or self.sites.get(target.split()[-1])
            if url:
                return url
        if allow_resolver and self.resolver is not None:
            url = self.resolver(target)
            if url and url.startswith(("http://", "https://")):
                if self.sites is not None:
                    self.sites.add(target, url)  # learn it
                return url
        return None

    def decide(self, event: Event) -> Intent | None:
        if not isinstance(event, VoiceEvent):
            return None
        text = event.text.lower().strip().rstrip(".!?")

        # "search <query> on youtube/google"
        m = re.search(r"\bsearch\s+(?:for\s+)?(.+?)\s+on\s+(youtube|google)\b", text)
        if m:
            return Intent(action="web_search",
                          parameters={"query": m.group(1).strip(), "engine": m.group(2)},
                          confidence=0.95)
        # "search youtube/google for <query>"
        m = re.search(r"\bsearch\s+(youtube|google)\s+for\s+(.+)", text)
        if m:
            return Intent(action="web_search",
                          parameters={"query": m.group(2).strip(), "engine": m.group(1)},
                          confidence=0.95)

        # Explicit navigation -> resolve via store or Gemini (and learn).
        m = re.search(rf"\b{_NAV}\s+(.+)", text)
        if m:
            url = self._resolve(m.group(1), allow_resolver=True)
            if url:
                return Intent(action="open_url", parameters={"url": url}, confidence=0.95)

        # "open/launch <X>": only a known site or a domain; else defer to Laya
        # (so "open firefox" launches the app, not a website).
        m = re.search(rf"\b{_OPEN}\s+(.+)", text)
        if m:
            url = self._resolve(m.group(1), allow_resolver=False)
            if url:
                return Intent(action="open_url", parameters={"url": url}, confidence=0.9)
            return None  # let Laya try open_app

        # "search [for] <query>" / "google <query>" -> google search.
        m = re.search(r"\b(?:search|google)\s+(?:for\s+)?(.+)", text)
        if m and not _OS_WORDS.search(text) and m.group(1).strip():
            return Intent(action="web_search",
                          parameters={"query": m.group(1).strip(), "engine": "google"},
                          confidence=0.9)
        return None
