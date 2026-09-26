"""Web dashboard backend (FastAPI + WebSocket).

The pipeline runs here and streams each step to the browser over a WebSocket;
the same UI-agnostic Pipeline.observer hook that fed the TUI feeds the web page.
Step 1 drives it with scripted events through the real decision→policy pipeline
(dry-run executor) so the page is live the moment you open it. Real inputs
(gesture/keyboard/voice) and real execution swap in later without touching the
frontend.

Run:  python -m controller.web        (serves http://127.0.0.1:8000)
"""

from __future__ import annotations

import asyncio
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from controller.audit.log import AuditLog
from controller.decision.schemas import GestureEvent, KeyboardEvent, VoiceEvent
from controller.os.base import ExecutionResult, OSController
from controller.pipeline import Pipeline
from controller.policy.validator import PolicyEngine

STATIC = Path(__file__).resolve().parent / "static"

# Scripted demo events: one per modality, plus a low-confidence swipe (denied)
# and unmapped speech (no intent) to show the failure states.
_DEMO_EVENTS = [
    VoiceEvent(text="switch to workspace three"),
    GestureEvent(name="swipe_right", confidence=0.95),
    VoiceEvent(text="volume up"),
    KeyboardEvent(key="MEDIA_PLAY_PAUSE"),
    GestureEvent(name="swipe_left", confidence=0.30),  # below threshold -> denied
    VoiceEvent(text="do a barrel roll"),               # unmapped -> no intent
]

_clients: set[WebSocket] = set()
_latest: dict = {}
# Recent entries, replayed to a newly opened tab so its event log isn't empty.
_history: deque[dict] = deque(maxlen=25)


class _DryRun(OSController):
    platform = "linux"

    def execute(self, intent) -> ExecutionResult:
        return ExecutionResult(status="success", detail="[dry-run]")


async def _broadcast(entry: dict) -> None:
    dead = []
    for ws in _clients:
        try:
            await ws.send_json(entry)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _clients.discard(ws)


async def _demo_loop() -> None:
    # Build the pipeline lazily to avoid importing config machinery at module load.
    from controller.main import build_rule_engine, load_config

    def observer(entry: dict) -> None:
        _latest.clear()
        _latest.update(entry)

    engine = build_rule_engine(load_config())
    pipeline = Pipeline(
        engine, PolicyEngine(platform="linux"), _DryRun(),
        AuditLog(stream=None), observer=observer,
    )
    await asyncio.sleep(0.5)
    while True:
        for event in _DEMO_EVENTS:
            pipeline.handle(event)          # observer fills _latest
            entry = dict(_latest)
            _history.append(entry)
            await _broadcast(entry)
            await asyncio.sleep(1.8)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    task = asyncio.create_task(_demo_loop())
    yield
    task.cancel()


app = FastAPI(lifespan=_lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    await websocket.accept()
    _clients.add(websocket)
    if _history:  # replay recent entries so a fresh tab isn't blank
        await websocket.send_json({"kind": "history", "entries": list(_history)})
    try:
        while True:
            await websocket.receive_text()  # keep the socket open
    except WebSocketDisconnect:
        _clients.discard(websocket)
