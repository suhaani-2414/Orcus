"""Platform and desktop-environment detection, isolated in one place."""

from __future__ import annotations

import os
import platform as _platform

from controller.actions.registry import LINUX, MACOS


def detect_platform() -> str:
    system = _platform.system()
    if system == "Linux":
        return LINUX
    if system == "Darwin":
        return MACOS
    return system.lower()


def detect_linux_wm() -> str | None:
    """Best-effort window-manager detection on Linux (e.g. 'hyprland')."""
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
    session = os.environ.get("XDG_SESSION_DESKTOP", "")
    hay = f"{desktop} {session}".lower()
    for wm in ("hyprland", "gnome", "kde", "sway"):
        if wm in hay:
            return wm
    return None
