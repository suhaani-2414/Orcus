"""Render the status UI headlessly to an SVG — lets us see the TUI without a
terminal. Optionally feeds a sample event so later steps show populated panels.

    python scripts/ui_snapshot.py out.svg [demo]
"""

from __future__ import annotations

import asyncio
import sys

from controller.ui.status import StatusApp


async def snap(path: str, demo: bool) -> None:
    app = StatusApp()
    async with app.run_test(size=(84, 28)) as pilot:
        if demo and hasattr(app, "show_event"):
            app.show_event(**DEMO)
        await pilot.pause()
        app.save_screenshot(path)


DEMO = {
    "platform": "linux / hyprland",
    "input_type": "voice",
    "raw": "switch to workspace three",
    "action": "switch_workspace",
    "confidence": 0.98,
    "execution": "success",
}


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "ui.svg"
    demo = len(sys.argv) > 2 and sys.argv[2] == "demo"
    asyncio.run(snap(out, demo))
    print(f"wrote {out}")
