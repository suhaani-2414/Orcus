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
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
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


async def _gesture_consumer(queue: asyncio.Queue) -> None:
    """Drain gesture events (from the camera thread) → pipeline → broadcast."""
    while True:
        event = await queue.get()
        await asyncio.to_thread(_get_voice_pipeline().handle, event)
        entry = dict(_latest)
        _history.append(entry)
        await _broadcast(entry)


def _gesture_worker(loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
    """Camera + MediaPipe swipe detection in a thread; hand events to the loop."""
    from controller.inputs.gestures import GestureInput

    try:
        print("gesture worker: opening camera…", flush=True)
        for event in GestureInput(show_window=False).events():
            print(f"gesture: {event.name} ({event.confidence})", flush=True)
            loop.call_soon_threadsafe(queue.put_nowait, event)
    except Exception as e:
        import traceback
        print(f"gesture capture stopped: {e}", flush=True)
        traceback.print_exc()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Warm the model + STT client in the background so the FIRST command isn't a
    # ~12s cold load. Server still starts instantly.
    async def _preload():
        try:
            await asyncio.to_thread(_get_voice_pipeline)
            await asyncio.to_thread(_get_recognizer().warm)
        except Exception as e:  # e.g. no API key yet — fine, it'll load on use
            print(f"preload skipped: {e}", flush=True)

    asyncio.create_task(_preload())

    # Live gesture capture (webcam swipes) when ORCUS_GESTURE=1.
    if os.environ.get("ORCUS_GESTURE") == "1":
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        asyncio.create_task(_gesture_consumer(queue))
        threading.Thread(target=_gesture_worker, args=(loop, queue), daemon=True).start()
        print("gesture capture: on (swipe left/right)", flush=True)

    yield


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


# --- Voice: /listen records a clip, transcribes (ElevenLabs Scribe), runs it
# through the real Laya pipeline, and broadcasts the result to all tabs. ---

_voice_pipeline = None
_recognizer = None
_recorder = None


def _voice_observer(entry: dict) -> None:
    _latest.clear()
    _latest.update(entry)


def _get_voice_pipeline() -> Pipeline:
    """Real Laya pipeline for voice. Dry-run unless ORCUS_EXECUTE=1. Built lazily
    (loads the model) so the server starts fast and only pays the cost on use."""
    global _voice_pipeline
    if _voice_pipeline is None:
        from controller.main import build_engine, load_config

        config = load_config()
        if os.environ.get("ORCUS_EXECUTE") == "1":
            from controller.os.factory import get_os_controller

            controller: OSController = get_os_controller()
        else:
            controller = _DryRun()
        engine = build_engine(config, use_laya=True)
        _voice_pipeline = Pipeline(
            engine,
            PolicyEngine(platform=controller.platform, min_confidence=config.get("min_confidence")),
            controller, AuditLog(stream=None), observer=_voice_observer,
        )
    return _voice_pipeline


def _get_recognizer():
    global _recognizer
    if _recognizer is None:
        from controller.inputs.voice import ScribeRecognizer

        _recognizer = ScribeRecognizer()
    return _recognizer


def _get_recorder():
    global _recorder
    if _recorder is None:
        from controller.inputs.voice import MicRecorder

        _recorder = MicRecorder()
    return _recorder


async def _transcribe_and_run(wav_path: str, record_secs: float) -> dict:
    """Shared tail: transcribe a WAV, run Laya, broadcast. Times each stage."""
    recognizer = _get_recognizer()
    t1 = time.time()
    try:
        text = await asyncio.to_thread(recognizer.transcribe, wav_path)
    except Exception as e:  # Scribe rejected the audio, network error, etc.
        print(f"voice: scribe error: {e}", flush=True)
        text = ""
    t2 = time.time()
    try:
        os.remove(wav_path)
    except OSError:
        pass
    if not text:
        print(f"voice: record={record_secs:.2f}s scribe={t2-t1:.2f}s (no transcript)", flush=True)
        return {"ok": False, "transcript": ""}

    await asyncio.to_thread(_get_voice_pipeline().handle, VoiceEvent(text=text))
    t3 = time.time()
    print(f"voice: record={record_secs:.2f}s scribe={t2-t1:.2f}s laya={t3-t2:.2f}s -> {text!r}",
          flush=True)
    entry = dict(_latest)
    _history.append(entry)
    await _broadcast(entry)
    return {"ok": True, "transcript": text}


# Hold-to-talk: /listen/start begins recording, /listen/stop ends it and runs
# the pipeline. The clip is only as long as you hold, cutting the old fixed 4s.
_record_started_at = 0.0


@app.post("/listen/start")
async def listen_start() -> dict:
    global _record_started_at
    try:
        _get_recorder().start()
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}
    _record_started_at = time.time()
    return {"ok": True}


def _wav_duration(path: str) -> float:
    """Seconds of audio in a WAV, or 0.0 if unreadable/empty/corrupt."""
    import contextlib
    import wave

    try:
        with contextlib.closing(wave.open(path)) as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except Exception:
        return 0.0


@app.post("/listen/stop")
async def listen_stop() -> dict:
    try:
        _get_recognizer()  # surfaces a missing API key before we bother recording
    except RuntimeError as e:
        _get_recorder().stop()
        return {"ok": False, "error": str(e)}
    wav = await asyncio.to_thread(_get_recorder().stop)
    if not wav:
        return {"ok": False, "error": "not recording"}

    # A too-short/empty clip is "corrupted" to Scribe (400) — reject it cleanly.
    if _wav_duration(wav) < 0.3:
        try:
            os.remove(wav)
        except OSError:
            pass
        return {"ok": False, "error": "too short — hold the button while you speak"}

    return await _transcribe_and_run(wav, time.time() - _record_started_at)


@app.post("/listen")
async def listen() -> dict:
    """Fixed-duration fallback (spacebar tap): record N seconds, then transcribe."""
    import tempfile

    from controller.inputs.voice import _record_wav

    try:
        recognizer = _get_recognizer()
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}
    wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    t0 = time.time()
    await asyncio.to_thread(_record_wav, wav, recognizer.record_seconds)
    return await _transcribe_and_run(wav, time.time() - t0)
