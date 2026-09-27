"""Console entry point for the ``orcus`` command.

The project is installed editable, so this command always imports the current
checkout rather than a copied release. Explicit CLI flags override the
always-on defaults.
"""

from __future__ import annotations

import sys
import os
import shutil
import socket
import threading
import time
import webbrowser
from pathlib import Path

from controller.main import main


def _open_dashboard(url: str) -> None:
    """Open the dashboard in Opera when installed, otherwise use the default."""
    opera_candidates = (
        "opera",
        "opera-stable",
        "opera-beta",
        "opera-developer",
        "/Applications/Opera.app/Contents/MacOS/Opera",
    )
    executable = next(
        (candidate for candidate in opera_candidates
         if Path(candidate).is_file() or shutil.which(candidate)),
        None,
    )
    if executable is not None:
        browser = webbrowser.BackgroundBrowser(executable)
        if browser.open(url):
            print("Opened Orcus in Opera.")
            return

    webbrowser.open(url)
    print("Opera was not found; opened Orcus in the default browser.")


def _port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.25)
        return probe.connect_ex((host, port)) == 0


def orcus() -> None:
    """Launch the current checkout's dashboard and always-on voice listener."""
    if len(sys.argv) > 1:
        main()
        return

    os.environ.setdefault("ORCUS_EXECUTE", "1")
    os.environ.setdefault("ORCUS_ALWAYS_ON", "1")
    os.environ.setdefault("ORCUS_GESTURE", "1")

    try:
        import uvicorn
    except ImportError as error:
        raise SystemExit(
            "The web frontend is not installed. Run: uv pip install -e '.[web]'"
        ) from error

    url = "http://127.0.0.1:8000"
    if _port_is_open("127.0.0.1", 8000):
        print(f"Orcus is already running at {url}; opening the existing dashboard.")
        _open_dashboard(url)
        return

    def open_dashboard() -> None:
        time.sleep(1.0)
        _open_dashboard(url)

    print(f"Starting Orcus dashboard at {url}")
    print("Always-on voice is enabled; say 'Orcus' followed by a command.")
    threading.Thread(target=open_dashboard, daemon=True).start()
    uvicorn.run("controller.web.server:app", host="127.0.0.1", port=8000, log_level="warning")
