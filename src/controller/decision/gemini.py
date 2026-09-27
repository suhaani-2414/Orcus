"""Gemini fallback parser for open-ended voice commands.

Laya classifies the fixed 15 actions fast and locally; the regex WebCommandEngine
catches obvious web phrasings. Gemini is the LAST voice fallback — it only fires
when those abstain, so common commands never pay its network latency. It parses
free-form speech ("pull up lofi beats on youtube") into a structured intent,
including free-text parameters Laya can't extract.

Needs GEMINI_API_KEY. The SDK import is lazy so this module loads without it
(tests subclass and override _raw).
"""

from __future__ import annotations

import json
import os

from controller.actions.registry import REGISTRY, get_action
from controller.decision.base import DecisionEngine
from controller.decision.schemas import Event, Intent, VoiceEvent


def _vocabulary() -> str:
    lines = []
    for spec in REGISTRY.values():
        props = spec.param_model.model_json_schema().get("properties", {})
        params = ", ".join(
            f"{n}: {p.get('type', 'string')}" + (f" ({'|'.join(p['enum'])})" if "enum" in p else "")
            for n, p in props.items()
        )
        lines.append(f"- {spec.name}({params}) — {spec.description}")
    return "\n".join(lines)


_INSTRUCTIONS = (
    "You translate a spoken computer command into ONE action.\n"
    "Reply ONLY with JSON: {{\"action\": <name or \"none\">, \"parameters\": {{...}}, "
    "\"confidence\": 0.0-1.0}}.\n"
    "Choose the single best action from this list; use \"none\" if it isn't a "
    "computer-control command.\n\nActions:\n{vocab}\n\nCommand: \"{text}\""
)


class GeminiDecisionEngine(DecisionEngine):
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise RuntimeError("set GEMINI_API_KEY to use the Gemini engine")
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _raw(self, prompt: str, as_json: bool = True) -> str:
        config = {"temperature": 0}
        if as_json:
            config["response_mime_type"] = "application/json"
        resp = self._get_client().models.generate_content(
            model=self.model, contents=prompt, config=config,
        )
        return resp.text or ""

    def resolve_url(self, name: str) -> str | None:
        """Resolve a spoken website name to its canonical https URL (or None).
        Used to learn new preferred sites on demand."""
        prompt = (
            "Return ONLY the canonical https:// URL for the website named "
            f"'{name}'. If it is not a real website, reply exactly 'none'. "
            "No prose, just the URL or 'none'."
        )
        try:
            text = self._raw(prompt, as_json=False).strip().strip('"').split()[0]
        except Exception:
            return None
        return text if text.startswith(("http://", "https://")) else None

    def decide(self, event: Event) -> Intent | None:
        if not isinstance(event, VoiceEvent):
            return None
        prompt = _INSTRUCTIONS.format(vocab=_vocabulary(), text=event.text[:500])
        try:
            data = json.loads(self._raw(prompt))
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

        if not isinstance(data, dict):
            return None
        action = data.get("action")
        parameters = data.get("parameters", {})
        if parameters is None:
            parameters = {}
        if not isinstance(action, str) or not isinstance(parameters, dict):
            return None
        if not action or action == "none" or get_action(action) is None:
            return None
        try:
            confidence = float(data.get("confidence", 0.0))
        except (TypeError, ValueError):
            return None
        if not 0.0 <= confidence <= 1.0:
            return None
        return Intent(
            action=action,
            parameters=parameters,
            confidence=confidence,
        )
