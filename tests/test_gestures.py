"""Swipe detector tests (no camera) + end-to-end gesture -> execution."""

import io
from types import SimpleNamespace

import pytest

from controller.audit.log import AuditLog
from controller.decision.rules import RuleBasedEngine
from controller.decision.schemas import GestureEvent
from controller.inputs.gesture_detector import MIN_TRAVEL, SwipeDetector
from controller.os.base import ExecutionResult, OSController
from controller.pipeline import Pipeline
from controller.policy.validator import PolicyEngine


def _landmarks():
    return [
        SimpleNamespace(x=0.0, y=0.0, z=0.0),
        *[SimpleNamespace(x=i / 20, y=i / 40, z=-i / 80) for i in range(1, 21)],
    ]


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


def test_static_landmark_normalization_is_translation_and_scale_invariant():
    np = pytest.importorskip("numpy")
    from controller.inputs.static_gestures import landmarks_to_vector

    base = _landmarks()
    shifted_scaled = [
        SimpleNamespace(x=2 + 3 * lm.x, y=-1 + 3 * lm.y, z=4 + 3 * lm.z)
        for lm in base
    ]
    assert np.allclose(landmarks_to_vector(base), landmarks_to_vector(shifted_scaled))


def test_static_classifier_requires_stable_predictions():
    pytest.importorskip("sklearn")
    from controller.inputs.static_gestures import StaticGestureClassifier

    classifier = StaticGestureClassifier(
        "models/gesture_knn.pkl", stable_frames=3, min_confidence=0.0
    )
    classifier.model.predict_proba = lambda _rows: [  # noqa: ARG005
        [1.0] + [0.0] * 8
    ]
    classifier.model.classes_ = list(range(9))
    assert classifier.update(_landmarks(), 0.0) is None
    assert classifier.update(_landmarks(), 0.1) is None
    assert classifier.update(_landmarks(), 0.2) == ("zero", 1.0)
    assert classifier.update(_landmarks(), 0.3) is None
    classifier.reset()
    assert classifier.update(_landmarks(), 1.0) is None


def test_static_classifier_ignores_open_palm_for_swipes():
    pytest.importorskip("sklearn")
    from controller.inputs.static_gestures import StaticGestureClassifier

    classifier = StaticGestureClassifier(
        "models/gesture_knn.pkl", stable_frames=2, min_confidence=0.0
    )
    classifier.model.predict_proba = lambda _rows: [  # noqa: ARG005
        [0.0] * 5 + [1.0] + [0.0] * 3
    ]
    classifier.model.classes_ = list(range(9))

    assert classifier.update(_landmarks(), 0.0) is None
    assert classifier.update(_landmarks(), 0.1) is None
