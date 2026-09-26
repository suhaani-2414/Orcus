from controller.decision.rules import RuleBasedEngine
from controller.decision.schemas import GestureEvent, KeyboardEvent, VoiceEvent

GESTURES = {"swipe_right": "next_workspace", "fist": "mute"}
KEYS = {"MEDIA_PLAY_PAUSE": "play_pause"}


def engine():
    return RuleBasedEngine(gesture_map=GESTURES, keyboard_map=KEYS)


def test_voice_switch_workspace_digit():
    intent = engine().decide(VoiceEvent(text="switch to workspace 3"))
    assert intent.action == "switch_workspace"
    assert intent.parameters == {"workspace": 3}


def test_voice_switch_workspace_word():
    intent = engine().decide(VoiceEvent(text="switch to workspace three"))
    assert intent.parameters == {"workspace": 3}


def test_voice_open_app():
    intent = engine().decide(VoiceEvent(text="open firefox"))
    assert intent.action == "open_app"
    assert intent.parameters == {"application": "firefox"}


def test_voice_volume_up():
    assert engine().decide(VoiceEvent(text="volume up")).action == "volume_up"


def test_gesture_maps_and_carries_confidence():
    intent = engine().decide(GestureEvent(name="swipe_right", confidence=0.91))
    assert intent.action == "next_workspace"
    assert intent.confidence == 0.91


def test_keyboard_maps_full_confidence():
    intent = engine().decide(KeyboardEvent(key="MEDIA_PLAY_PAUSE"))
    assert intent.action == "play_pause"
    assert intent.confidence == 1.0


def test_unmapped_voice_returns_none():
    assert engine().decide(VoiceEvent(text="do a barrel roll")) is None


def test_unmapped_gesture_returns_none():
    assert engine().decide(GestureEvent(name="wiggle", confidence=0.99)) is None
