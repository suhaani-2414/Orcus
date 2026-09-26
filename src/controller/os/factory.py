"""Selects the OS controller once at startup, so no OS branching leaks elsewhere."""

from __future__ import annotations

from controller.actions.registry import LINUX, MACOS
from controller.os.base import OSController
from controller.os.platform import detect_platform


def get_os_controller(platform: str | None = None) -> OSController:
    platform = platform or detect_platform()
    if platform == LINUX:
        from controller.os.linux.controller import LinuxController

        return LinuxController()
    if platform == MACOS:
        from controller.os.macos.controller import MacOSController

        return MacOSController()
    raise RuntimeError(f"no OS controller for platform: {platform}")
