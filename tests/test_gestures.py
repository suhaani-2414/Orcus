"""Swipe detector tests (no camera) + end-to-end gesture -> execution."""

import io

from controller.audit.log import AuditLog
from controller.decision.rules import RuleBasedEngine
from controller.decision.schemas import GestureEvent
from controller.inputs.gesture_detector import MIN_TRAVEL, SwipeDetector
from controller.os.base import ExecutionResult, OSController
from controller.pipeline import Pipeline
from controller.policy.validator import PolicyEngine


def feed(points):
    d = SwipeDetector()
    hit = None
    for t, x, y in points:
        r = d.update(t, x, y)
        if r:
            hit = r
    return hit


def test_rightward_swipe_detected():
    hit = feed([(i * 0.05, 0.2 + 0.5 * i / 5, 0.5) for i in range(6)])
    assert hit is not None and hit[0] == "swipe_right"


def test_leftward_swipe_detected():
    hit = feed([(i * 0.05, 0.8 - 0.5 * i / 5, 0.5) for i in range(6)])
    assert hit is not None and hit[0] == "swipe_left"


def test_jitter_ignored():
    assert feed([(i * 0.05, 0.5 + 0.01 * (i % 2), 0.5) for i in range(6)]) is None


def test_swipe_down_detected():
    hit = feed([(i * 0.05, 0.5, 0.2 + 0.5 * i / 5) for i in range(6)])
    assert hit is not None and hit[0] == "swipe_down"


def test_swipe_up_detected():
    hit = feed([(i * 0.05, 0.5, 0.8 - 0.5 * i / 5) for i in range(6)])
    assert hit is not None and hit[0] == "swipe_up"


def test_too_slow_ignored():
    assert feed([(i * 0.24, 0.2 + 0.5 * i / 5, 0.5) for i in range(6)]) is None


def test_confidence_in_policy_passing_range():
    _, conf = feed([(i * 0.04, 0.15 + 0.6 * i / 5, 0.5) for i in range(6)])
    assert 0.7 <= conf <= 0.99  # clean horizontal swipe clears policy threshold


def test_cooldown_prevents_double_fire():
    d = SwipeDetector()
    fires = 0
    # Two back-to-back rightward sweeps within the cooldown window.
    for i in range(12):
        r = d.update(i * 0.05, 0.2 + 0.5 * (i % 6) / 5, 0.5)
        if r:
            fires += 1
    assert fires == 1


class RecordingController(OSController):
    platform = "linux"

    def __init__(self):
        self.executed = []

    def execute(self, intent):
        self.executed.append(intent)
        return ExecutionResult(status="success")


def test_gesture_event_flows_to_execution():
    ctrl = RecordingController()
    engine = RuleBasedEngine(
        gesture_map={"swipe_right": "next_workspace", "swipe_left": "previous_workspace"},
        keyboard_map={},
    )
    pipeline = Pipeline(engine, PolicyEngine(platform="linux"), ctrl, AuditLog(stream=io.StringIO()))
    # Simulate what GestureInput yields.
    pipeline.handle(GestureEvent(name="swipe_right", confidence=0.9))
    assert ctrl.executed[0].action == "next_workspace"
