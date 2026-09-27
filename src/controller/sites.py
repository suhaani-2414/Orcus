"""Preferred-sites store: spoken name -> URL, for direct navigation.

"go to youtube" opens youtube.com instead of googling "youtube". Seeded with
common sites; unknown names are resolved by Gemini and saved here so the next
request is instant.
"""

from __future__ import annotations

import json
from pathlib import Path

_STORE_PATH = Path(__file__).resolve().parents[2] / "config" / "sites.json"

DEFAULT_SITES: dict[str, str] = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "reddit": "https://www.reddit.com",
    "maps": "https://maps.google.com",
    "google maps": "https://maps.google.com",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "netflix": "https://www.netflix.com",
    "amazon": "https://www.amazon.com",
    "wikipedia": "https://www.wikipedia.org",
    "stack overflow": "https://stackoverflow.com",
    "linkedin": "https://www.linkedin.com",
    "hacker news": "https://news.ycombinator.com",
    "twitch": "https://www.twitch.tv",
}


class SiteStore:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else _STORE_PATH
        self.sites = dict(DEFAULT_SITES)
        if self.path.exists():
            try:
                self.sites.update(json.loads(self.path.read_text()))
            except (OSError, ValueError):
                pass

    def get(self, name: str) -> str | None:
        return self.sites.get(name.strip().lower())

    def add(self, name: str, url: str) -> None:
        self.sites[name.strip().lower()] = url
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.sites, indent=2, sort_keys=True))
        except OSError:
            pass

    def names(self) -> list[str]:
        return sorted(self.sites)
