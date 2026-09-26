import io

from controller.audit.log import AuditLog
from controller.decision.rules import RuleBasedEngine
from controller.decision.schemas import GestureEvent, VoiceEvent
from controller.os.base import ExecutionResult, OSController
from controller.pipeline import Pipeline
from controller.policy.validator import PolicyEngine


class RecordingController(OSController):
    platform = "linux"

    def __init__(self):
        self.executed = []

    def execute(self, intent):
        self.executed.append(intent)
        return ExecutionResult(status="success", detail="ok")


def build(controller):
    engine = RuleBasedEngine(
        gesture_map={"swipe_right": "next_workspace"}, keyboard_map={}
    )
    policy = PolicyEngine(platform="linux")
    audit = AuditLog(stream=io.StringIO())
    return Pipeline(engine, policy, controller, audit)


def test_end_to_end_voice_executes():
    ctrl = RecordingController()
    result = build(ctrl).handle(VoiceEvent(text="switch to workspace 3"))
    assert result.status == "success"
    assert ctrl.executed[0].action == "switch_workspace"
    assert ctrl.executed[0].parameters == {"workspace": 3}


def test_gesture_flows_to_execution():
    ctrl = RecordingController()
    build(ctrl).handle(GestureEvent(name="swipe_right", confidence=0.95))
    assert ctrl.executed[0].action == "next_workspace"


def test_unmapped_event_does_not_execute():
    ctrl = RecordingController()
    result = build(ctrl).handle(VoiceEvent(text="make me a sandwich"))
    assert result.status == "error"
    assert ctrl.executed == []


def test_low_confidence_gesture_blocked_by_policy():
    ctrl = RecordingController()
    result = build(ctrl).handle(GestureEvent(name="swipe_right", confidence=0.3))
    assert result.status == "error"
    assert ctrl.executed == []
