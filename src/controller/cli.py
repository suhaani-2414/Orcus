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

from controller.config import load_env_file
from controller.main import main

_instance_lock = None


def _acquire_instance_lock() -> bool:
    """Keep one dashboard process responsible for camera/microphone ownership."""
    global _instance_lock
    try:
        import fcntl

        lock_path = Path(os.environ.get("ORCUS_LOCK_FILE", "/tmp/orcus.lock"))
        _instance_lock = lock_path.open("w")
        fcntl.flock(_instance_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (BlockingIOError, OSError):
        if _instance_lock is not None:
            _instance_lock.close()
            _instance_lock = None
        return False


def _open_dashboard(url: str) -> None:
    """Open the dashboard in the system default browser, reusing an existing
    window/tab (new=0) so repeat launches don't spawn extra browser windows."""
    if os.environ.get("ORCUS_NO_BROWSER") == "1":
        print(f"Orcus dashboard: {url}")
        return
    try:
        webbrowser.open(url, new=0, autoraise=True)
    except Exception:
        pass
    print(f"Orcus dashboard: {url}")


def _port_is_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.25)
        return probe.connect_ex((host, port)) == 0


def orcus() -> None:
    """Launch the current checkout's dashboard and always-on voice listener."""
    load_env_file()
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
    if not _acquire_instance_lock():
        print(f"Orcus is already running at {url}; opening the existing dashboard.")
        threading.Thread(target=_open_dashboard, args=(url,), daemon=True).start()
        return
    if _port_is_open("127.0.0.1", 8000):
        print(f"Orcus is already running at {url}; opening the existing dashboard.")
        threading.Thread(target=_open_dashboard, args=(url,), daemon=True).start()
        return

    def open_dashboard() -> None:
        time.sleep(1.0)
        _open_dashboard(url)

    print(f"Starting Orcus dashboard at {url}")
    print("Always-on voice is enabled; say 'Orcus' followed by a command.")
    threading.Thread(target=open_dashboard, daemon=True).start()
    uvicorn.run("controller.web.server:app", host="127.0.0.1", port=8000, log_level="warning")
