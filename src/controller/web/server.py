"""Web dashboard backend (FastAPI + WebSocket).

The pipeline runs here and streams each step to the browser over a WebSocket;
the same UI-agnostic Pipeline.observer hook that fed the TUI feeds the web page.
The dashboard shows only REAL events: voice via the /listen endpoint (mic →
ElevenLabs Scribe → Laya). It starts empty and fills as you speak.

Run:  python -m controller.web        (serves http://127.0.0.1:8000)
"""

from __future__ import annotations

import asyncio
import os
from collections import deque
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from controller.audit.log import AuditLog
from controller.decision.schemas import VoiceEvent
from controller.os.base import ExecutionResult, OSController
from controller.pipeline import Pipeline
from controller.policy.validator import PolicyEngine

STATIC = Path(__file__).resolve().parent / "static"

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


app = FastAPI()
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


# --- Voice: /listen records a clip, transcribes (ElevenLabs Scribe), runs it
# through the real Laya pipeline, and broadcasts the result to all tabs. ---

_voice_pipeline = None
_recognizer = None


def _voice_observer(entry: dict) -> None:
    _latest.clear()
    _latest.update(entry)


def _get_voice_pipeline() -> Pipeline:
    """Real Laya pipeline for voice. Dry-run unless ORCUS_EXECUTE=1. Built lazily
    (loads the model) so the server starts fast and only pays the cost on use."""
    global _voice_pipeline
    if _voice_pipeline is None:
        from controller.main import build_engine, load_config

        if os.environ.get("ORCUS_EXECUTE") == "1":
            from controller.os.factory import get_os_controller

            controller: OSController = get_os_controller()
        else:
            controller = _DryRun()
        engine = build_engine(load_config(), use_laya=True)
        _voice_pipeline = Pipeline(
            engine, PolicyEngine(platform=controller.platform), controller,
            AuditLog(stream=None), observer=_voice_observer,
        )
    return _voice_pipeline


def _get_recognizer():
    global _recognizer
    if _recognizer is None:
        from controller.inputs.voice import ScribeRecognizer

        _recognizer = ScribeRecognizer()
    return _recognizer


@app.post("/listen")
async def listen() -> dict:
    try:
        recognizer = _get_recognizer()  # raises if ELEVENLABS_API_KEY is unset
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}

    # Recording + STT + model inference are blocking; keep them off the event loop.
    text = await asyncio.to_thread(recognizer.listen)
    if not text:
        return {"ok": False, "transcript": ""}

    await asyncio.to_thread(_get_voice_pipeline().handle, VoiceEvent(text=text))
    entry = dict(_latest)
    _history.append(entry)
    await _broadcast(entry)
    return {"ok": True, "transcript": text}
