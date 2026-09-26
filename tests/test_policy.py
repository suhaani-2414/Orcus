from controller.decision.schemas import Intent
from controller.policy.validator import PolicyEngine


def linux_policy(confirm=None):
    return PolicyEngine(platform="linux", confirm=confirm)


def test_allows_valid_intent():
    d = linux_policy().evaluate(
        Intent(action="switch_workspace", parameters={"workspace": 3}, confidence=0.95)
    )
    assert d.allowed
    assert d.normalized_parameters == {"workspace": 3}


def test_rejects_unknown_action():
    d = linux_policy().evaluate(Intent(action="format_disk", confidence=1.0))
    assert not d.allowed
    assert "unknown action" in d.reason


def test_rejects_invalid_parameters():
    d = linux_policy().evaluate(
        Intent(action="switch_workspace", parameters={"workspace": 999}, confidence=0.95)
    )
    assert not d.allowed
    assert "invalid parameters" in d.reason


def test_rejects_extra_parameters():
    d = linux_policy().evaluate(
        Intent(action="mute", parameters={"sudo": True}, confidence=0.95)
    )
    assert not d.allowed


def test_rejects_low_confidence():
    d = linux_policy().evaluate(Intent(action="mute", confidence=0.2))
    assert not d.allowed
    assert "confidence" in d.reason


def test_unsupported_on_platform():
    # lock_screen is supported everywhere, but simulate an unknown platform.
    d = PolicyEngine(platform="plan9").evaluate(Intent(action="mute", confidence=0.95))
    assert not d.allowed
    assert "unsupported" in d.reason


def test_destructive_denied_by_default():
    d = linux_policy().evaluate(Intent(action="lock_screen", confidence=0.99))
    assert not d.allowed
    assert "not confirmed" in d.reason


def test_destructive_allowed_when_confirmed():
    d = linux_policy(confirm=lambda i, s: True).evaluate(
        Intent(action="lock_screen", confidence=0.99)
    )
    assert d.allowed
