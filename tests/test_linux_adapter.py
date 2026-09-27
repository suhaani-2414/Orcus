from controller.decision.schemas import Intent
from controller.os.linux.controller import LinuxController


def fake_runner(record):
    def run(argv):
        record.append(argv)
        return 0, ""
    return run


def test_switch_workspace_builds_hyprctl_command():
    calls = []
    ctrl = LinuxController(runner=fake_runner(calls))
    result = ctrl.execute(Intent(action="switch_workspace", parameters={"workspace": 3}, confidence=1.0))
    assert result.status == "success"
    assert calls == [["hyprctl", "dispatch", "workspace", "3"]]


def test_volume_up_uses_wpctl_with_amount():
    calls = []
    ctrl = LinuxController(runner=fake_runner(calls))
    ctrl.execute(Intent(action="volume_up", parameters={"amount": 10}, confidence=1.0))
    assert calls == [["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "10%+"]]


def test_close_app_kills_active():
    calls = []
    LinuxController(runner=fake_runner(calls)).execute(Intent(action="close_app", confidence=1.0))
    assert calls == [["hyprctl", "dispatch", "killactive"]]


def test_move_window_maps_direction():
    calls = []
    LinuxController(runner=fake_runner(calls)).execute(
        Intent(action="move_window", parameters={"direction": "left"}, confidence=1.0)
    )
    assert calls == [["hyprctl", "dispatch", "movewindow", "l"]]


def test_resize_window_shrink():
    calls = []
    LinuxController(runner=fake_runner(calls)).execute(
        Intent(action="resize_window", parameters={"mode": "shrink"}, confidence=1.0)
    )
    assert calls == [["hyprctl", "dispatch", "resizeactive", "-100", "-100"]]


def test_still_unsupported_action_reports_unsupported():
    ctrl = LinuxController(runner=fake_runner([]))
    # move_window with no params uses the model default and IS supported now,
    # so use an action the adapter genuinely doesn't implement.
    result = ctrl.execute(Intent(action="switch_workspace_totally_fake", confidence=1.0))
    assert result.status == "unsupported"


def test_nonzero_exit_reports_error():
    def failing(argv):
        return 1, "boom"
    ctrl = LinuxController(runner=failing)
    result = ctrl.execute(Intent(action="mute", confidence=1.0))
    assert result.status == "error"
    assert result.detail == "boom"
