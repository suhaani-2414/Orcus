"""Voice input tests with a fake recognizer — no API key, mic, or network."""

import io

import pytest

from controller.audit.log import AuditLog
from controller.decision.rules import RuleBasedEngine
from controller.inputs.voice import (
    AlwaysOnVoiceInput,
    ScribeRecognizer,
    SpeechRecognizer,
    VoiceInput,
)
from controller.os.base import ExecutionResult, OSController
from controller.pipeline import Pipeline
from controller.policy.validator import PolicyEngine


class FakeRecognizer(SpeechRecognizer):
    def __init__(self, transcripts):
        self._q = list(transcripts)

    def listen(self) -> str:
        return self._q.pop(0) if self._q else ""


def test_voice_input_yields_event_from_transcript():
    src = VoiceInput(FakeRecognizer(["switch to workspace three"]), prompt=False)
    event = next(src.events())
    assert event.type == "voice"
    assert event.text == "switch to workspace three"


def test_empty_transcript_is_skipped():
    # First transcript is empty (skipped), second is real.
    src = VoiceInput(FakeRecognizer(["", "volume up"]), prompt=False)
    event = next(src.events())
    assert event.text == "volume up"


def test_voice_flows_through_pipeline_to_execution():
    class Recorder(OSController):
        platform = "linux"

        def __init__(self):
            self.executed = []

        def execute(self, intent):
            self.executed.append(intent)
            return ExecutionResult(status="success")

    ctrl = Recorder()
    engine = RuleBasedEngine(gesture_map={}, keyboard_map={})
    pipeline = Pipeline(engine, PolicyEngine(platform="linux"), ctrl, AuditLog(stream=io.StringIO()))

    src = VoiceInput(FakeRecognizer(["switch to workspace 3"]), prompt=False)
    pipeline.handle(next(src.events()))
    assert ctrl.executed[0].action == "switch_workspace"
    assert ctrl.executed[0].parameters == {"workspace": 3}


def test_scribe_recognizer_requires_api_key(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ELEVENLABS_API_KEY"):
        ScribeRecognizer()


def test_scribe_synthesize_uses_tts_client(monkeypatch):
    recognizer = ScribeRecognizer(api_key="test")

    class FakeTTS:
        def convert(self, **kwargs):
            assert kwargs["text"] == "Volume increased."
            return [b"mp3", b"-audio"]

    class FakeClient:
        text_to_speech = FakeTTS()

    recognizer._client = FakeClient()
    assert recognizer.synthesize("Volume increased.") == b"mp3-audio"


class ChunkRecognizer:
    def __init__(self, transcripts):
        self.transcripts = iter(transcripts)

    def listen_chunk(self, _seconds):
        return next(self.transcripts, "")


def test_always_on_requires_wake_phrase():
    source = AlwaysOnVoiceInput(
        ChunkRecognizer(["volume up", "orca volume down"]),
        chunk_seconds=0.01,
    )
    event = next(source.events())
    assert event.text == "volume down"


def test_always_on_supports_two_step_activation():
    source = AlwaysOnVoiceInput(
        ChunkRecognizer(["hey orca", "switch to workspace 3"]),
        chunk_seconds=0.01,
    )
    event = next(source.events())
    assert event.text == "switch to workspace 3"


def test_always_on_ignores_unrelated_after_activation_timeout(monkeypatch):
    import controller.inputs.voice as voice

    now = iter([0.0, 10.0, 20.0])
    monkeypatch.setattr(voice.time, "monotonic", lambda: next(now))
    source = AlwaysOnVoiceInput(
        ChunkRecognizer(["orca", "volume up", "orca volume down"]),
        chunk_seconds=0.01,
    )
    event = next(source.events())
    assert event.text == "volume down"
