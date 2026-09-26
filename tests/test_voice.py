"""Voice input tests with a fake recognizer — no API key, mic, or network."""

import io

import pytest

from controller.audit.log import AuditLog
from controller.decision.rules import RuleBasedEngine
from controller.inputs.voice import ScribeRecognizer, SpeechRecognizer, VoiceInput
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
