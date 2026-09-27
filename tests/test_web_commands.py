"""WebCommandEngine (regex) + Gemini fallback (fake) + adapter URL building."""

import json

from controller.decision.gemini import GeminiDecisionEngine
from controller.decision.schemas import GestureEvent, VoiceEvent
from controller.decision.web_commands import WebCommandEngine
from controller.os.linux.controller import LinuxController, _normalize_url, _search_url


# --- regex web commands ---
def web():
    return WebCommandEngine()


def test_search_on_youtube():
    i = web().decide(VoiceEvent(text="search lofi beats on youtube"))
    assert i.action == "web_search"
    assert i.parameters == {"query": "lofi beats", "engine": "youtube"}


def test_search_for_google():
    i = web().decide(VoiceEvent(text="search for weather in boston"))
    assert i.action == "web_search"
    assert i.parameters["engine"] == "google"
    assert "weather" in i.parameters["query"]


def test_open_url_needs_a_domain():
    i = web().decide(VoiceEvent(text="open github.com"))
    assert i.action == "open_url" and i.parameters == {"url": "github.com"}


def test_open_app_not_captured_as_url():
    # "open opera" has no dot -> falls through to Laya/rules, not open_url.
    assert web().decide(VoiceEvent(text="open opera")) is None


def test_switch_workspace_not_hijacked_by_search():
    assert web().decide(VoiceEvent(text="switch workspace three")) is None


def test_web_engine_ignores_gestures():
    assert web().decide(GestureEvent(name="fist", confidence=0.9)) is None


# --- adapter URL building ---
def test_search_url_youtube():
    assert "youtube.com/results" in _search_url("cats", "youtube")


def test_normalize_url_adds_scheme():
    assert _normalize_url("github.com") == "https://github.com"
    assert _normalize_url("https://x.com") == "https://x.com"


def test_linux_adapter_web_search_uses_xdg_open():
    calls = []
    LinuxController(runner=lambda a: (calls.append(a), (0, ""))[1]).execute(
        __import__("controller.decision.schemas", fromlist=["Intent"]).Intent(
            action="web_search", parameters={"query": "cats", "engine": "youtube"}, confidence=1.0
        )
    )
    assert calls[0][0] == "xdg-open" and "youtube.com" in calls[0][1]


# --- Gemini fallback (no key/network) ---
class FakeGemini(GeminiDecisionEngine):
    def __init__(self, payload):
        self._payload = payload  # skip real __init__ (no key needed)
        self.model = "fake"

    def _raw(self, prompt):
        return json.dumps(self._payload)


def test_gemini_parses_free_form_into_intent():
    eng = FakeGemini({"action": "web_search",
                      "parameters": {"query": "jazz", "engine": "youtube"}, "confidence": 0.88})
    i = eng.decide(VoiceEvent(text="pull up some jazz on youtube"))
    assert i.action == "web_search" and i.parameters["query"] == "jazz"
    assert i.confidence == 0.88


def test_gemini_none_yields_no_intent():
    assert FakeGemini({"action": "none"}).decide(VoiceEvent(text="what a nice day")) is None


def test_gemini_rejects_unknown_action():
    assert FakeGemini({"action": "format_disk"}).decide(VoiceEvent(text="wipe it")) is None
