"""Laya engine tests with a fake client mirroring rl_agent_api.system_one output.

No torch or model weights required: we assert the wiring (registry -> choice
question -> Intent + params), not the model's accuracy.
"""

from controller.decision.composite import CompositeEngine
from controller.decision.laya import NONE_OPTION, LayaDecisionEngine
from controller.decision.rules import RuleBasedEngine
from controller.decision.schemas import GestureEvent, KeyboardEvent, VoiceEvent


class FakeLaya:
    """Returns a preset choice/confidence in Laya's answer shape."""

    def __init__(self, choice, confidence=0.95):
        self.choice = choice
        self.confidence = confidence
        self.last_questions = None

    def system_one(self, state, questions):
        self.last_questions = questions
        qid = next(iter(questions))
        return {
            "model": "rl-agent",
            "answers": {
                qid: {
                    "type": "choice",
                    "choice": self.choice,
                    "confidence": self.confidence,
                }
            },
        }


def test_voice_classified_into_registry_action():
    engine = LayaDecisionEngine(FakeLaya("switch_workspace", 0.97))
    intent = engine.decide(VoiceEvent(text="jump over to workspace 3 please"))
    assert intent.action == "switch_workspace"
    assert intent.parameters == {"workspace": 3}
    assert intent.confidence == 0.97


def test_confidence_comes_from_laya():
    engine = LayaDecisionEngine(FakeLaya("mute", 0.61))
    assert engine.decide(VoiceEvent(text="silence")).confidence == 0.61


def test_none_option_yields_no_intent():
    engine = LayaDecisionEngine(FakeLaya(NONE_OPTION))
    assert engine.decide(VoiceEvent(text="do a barrel roll")) is None


def test_choice_set_includes_registry_and_none():
    fake = FakeLaya("mute")
    LayaDecisionEngine(fake).decide(VoiceEvent(text="hush"))
    criteria = fake.last_questions["action"]["criteria"]
    assert "mute" in criteria and "switch_workspace" in criteria
    assert NONE_OPTION in criteria


def test_allow_none_false_omits_none_option():
    fake = FakeLaya("mute")
    LayaDecisionEngine(fake, allow_none=False).decide(VoiceEvent(text="hush"))
    criteria = fake.last_questions["action"]["criteria"]
    assert NONE_OPTION not in criteria
    assert "mute" in criteria


def test_ignores_non_voice_events():
    engine = LayaDecisionEngine(FakeLaya("mute"))
    assert engine.decide(GestureEvent(name="fist", confidence=0.9)) is None
    assert engine.decide(KeyboardEvent(key="MEDIA_PLAY_PAUSE")) is None


def test_composite_routes_voice_to_laya_and_gesture_to_rules():
    laya = LayaDecisionEngine(FakeLaya("volume_up", 0.9))
    rules = RuleBasedEngine(
        gesture_map={"swipe_right": "next_workspace"}, keyboard_map={}
    )
    engine = CompositeEngine([laya, rules])

    # Voice handled by Laya.
    assert engine.decide(VoiceEvent(text="turn it up")).action == "volume_up"
    # Gesture skipped by Laya, handled by rules.
    assert engine.decide(GestureEvent(name="swipe_right", confidence=0.95)).action == "next_workspace"


def test_composite_falls_back_to_rules_when_laya_declines():
    laya = LayaDecisionEngine(FakeLaya(NONE_OPTION))
    rules = RuleBasedEngine(gesture_map={}, keyboard_map={})
    engine = CompositeEngine([laya, rules])
    # Laya says none; rule engine still parses the voice command.
    intent = engine.decide(VoiceEvent(text="volume up"))
    assert intent.action == "volume_up"
