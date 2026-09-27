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
import re
import shutil
import subprocess
import threading
import time
import tempfile
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
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
_metrics: deque[dict] = deque(maxlen=500)
_runtime_lock = threading.Lock()
_runtime = {
    "camera": {"state": "off", "error": None, "last_frame": None},
    "voice": {"state": "off", "error": None},
    "pipeline": {"state": "idle", "error": None},
    "preload": {"state": "pending", "error": None},
}


class GestureMappingRequest(BaseModel):
    mappings: dict[str, str | None]


class ConfirmationRequest(BaseModel):
    confirmed: bool


class SpeakRequest(BaseModel):
    text: str


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
        try:
            await asyncio.to_thread(_get_voice_pipeline().handle, event)
            entry = dict(_latest)
            _history.append(entry)
            await _broadcast(entry)
        except Exception as error:
            _set_runtime("pipeline", state="error", error=str(error))


_latest_frame: bytes | None = None  # latest camera JPEG for the preview


def _frame_sink(frame) -> None:
    """Store the latest annotated frame as JPEG for the /camera preview."""
    global _latest_frame
    import cv2

    h, w = frame.shape[:2]
    if w > 480:  # downscale to keep encode/stream light
        frame = cv2.resize(frame, (480, int(480 * h / w)))
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
    if ok:
        _latest_frame = buf.tobytes()
        _set_runtime("camera", state="running", error=None, last_frame=time.time())


def _set_runtime(component: str, **values) -> None:
    with _runtime_lock:
        _runtime[component].update(values)


def _runtime_snapshot() -> dict:
    with _runtime_lock:
        return {name: dict(values) for name, values in _runtime.items()}


def _gesture_worker(loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
    """Camera + MediaPipe swipe detection in a thread; hand events to the loop."""
    from controller.inputs.gestures import GestureInput

    from controller.main import load_config

    settings = load_config().get("gesture_settings") or {}
    _set_runtime("camera", state="starting", error=None)
    while not _gesture_stop.is_set():
        try:
            print("gesture worker: opening camera…", flush=True)
            source = GestureInput(
                show_window=False,
                frame_sink=_frame_sink,
                **{key: value for key, value in settings.items()
                   if key in {
                       "static_min_confidence", "static_stable_frames",
                       "static_cooldown_seconds", "swipe_min_travel",
                       "swipe_cooldown_seconds", "camera_index",
                   }},
            )
            _set_runtime("camera", state="running", error=None)
            for event in source.events():
                if _gesture_stop.is_set():
                    break
                print(f"gesture: {event.name} ({event.confidence})", flush=True)
                loop.call_soon_threadsafe(queue.put_nowait, event)
        except Exception as error:
            _set_runtime("camera", state="error", error=str(error))
            print(f"gesture capture retrying: {error}", flush=True)
            _gesture_stop.wait(2.0)
        finally:
            _set_runtime("camera", state="stopped" if _gesture_stop.is_set() else "retrying")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Warm the model + STT client in the background so the FIRST command isn't a
    # ~12s cold load. Server still starts instantly.
    async def _preload():
        try:
            await asyncio.to_thread(_get_voice_pipeline)
            await asyncio.to_thread(_get_recognizer().warm)
            _set_runtime("preload", state="ready", error=None)
        except Exception as e:  # e.g. no API key yet — fine, it'll load on use
            _set_runtime("preload", state="error", error=str(e))
            print(f"preload skipped: {e}", flush=True)

    asyncio.create_task(_preload())

    # Live gesture capture (webcam swipes) when ORCUS_GESTURE=1.
    if os.environ.get("ORCUS_GESTURE") == "1":
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        asyncio.create_task(_gesture_consumer(queue))
        _gesture_stop.clear()
        threading.Thread(target=_gesture_worker, args=(loop, queue), daemon=True,
                         name="orcus-camera").start()
        print("gesture capture: on (swipe left/right)", flush=True)

    if os.environ.get("ORCUS_ALWAYS_ON") == "1":
        voice_status = await always_on_start()  # creates the queue+consumer itself
        if voice_status.get("active"):
            print("always-on voice: on", flush=True)
        else:
            print(
                f"always-on voice: unavailable ({voice_status.get('error', 'not started')})",
                flush=True,
            )

    yield
    _gesture_stop.set()
    _always_on_stop.set()
    if _always_on_source is not None:
        _always_on_source.stop()


app = FastAPI(lifespan=_lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/camera")
async def camera():
    """MJPEG stream of the gesture camera (with hand landmarks). Only produces
    frames when gesture capture is running (ORCUS_GESTURE=1)."""
    from fastapi.responses import StreamingResponse

    async def frames():
        boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
        while True:
            if _latest_frame is not None:
                yield boundary + _latest_frame + b"\r\n"
            await asyncio.sleep(1 / 15)  # ~15 fps cap

    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/status")
async def runtime_status() -> dict:
    return _runtime_snapshot()


@app.get("/api/metrics")
async def runtime_metrics() -> dict:
    samples = list(_metrics)
    totals = [sample.get("total") for sample in samples if sample.get("total") is not None]
    if not totals:
        return {"samples": 0, "average_total_ms": None, "p95_total_ms": None}
    totals.sort()
    p95_index = min(len(totals) - 1, int(len(totals) * 0.95))
    return {
        "samples": len(totals),
        "average_total_ms": round(sum(totals) / len(totals), 2),
        "p95_total_ms": round(totals[p95_index], 2),
    }


@app.get("/api/setup")
async def setup_status() -> dict:
    """Return safe first-run diagnostics without exposing credentials."""
    from controller.main import load_config

    config = load_config()
    return {
        "execution_enabled": os.environ.get("ORCUS_EXECUTE") == "1",
        "voice_key_configured": bool(os.environ.get("ELEVENLABS_API_KEY")),
        "camera_index": (config.get("gesture_settings") or {}).get("camera_index", 0),
        "gesture_settings": config.get("gesture_settings") or {},
        "wake_word": os.environ.get("ORCUS_WAKE_WORD", "computer"),
        "confirmation_timeout_seconds": config.get("confirmation_timeout_seconds", 30),
        "gemini_configured": bool(os.environ.get("GEMINI_API_KEY")),
        "tts_enabled": os.environ.get("ORCUS_TTS", "1") != "0",
        "runtime": _runtime_snapshot(),
    }


@app.get("/api/devices")
async def device_status() -> dict:
    cameras = []
    try:
        import cv2

        for index in range(4):
            capture = cv2.VideoCapture(index)
            if capture.isOpened():
                cameras.append({"index": index, "available": True})
            capture.release()
    except Exception:
        cameras = []

    microphones = []
    if shutil.which("arecord"):
        result = await asyncio.to_thread(
            subprocess.run, ["arecord", "-l"], capture_output=True, text=True, check=False
        )
        microphones = [
            line.strip() for line in result.stdout.splitlines()
            if line.strip().startswith("card ")
        ]
    return {
        "cameras": cameras,
        "microphones": microphones,
        "recorders": [name for name in ("arecord", "ffmpeg") if shutil.which(name)],
    }


@app.post("/api/voice/speak")
async def voice_speak(request: SpeakRequest):
    """Generate optional ElevenLabs audio for browser playback."""
    if os.environ.get("ORCUS_TTS", "1") == "0":
        return {"ok": False, "error": "spoken feedback disabled"}
    try:
        audio = await asyncio.to_thread(_get_recognizer().synthesize, request.text)
    except Exception as error:
        _set_runtime("voice", state="error", error=f"TTS: {error}")
        return {"ok": False, "error": str(error)}
    from fastapi.responses import Response

    return Response(content=audio, media_type="audio/mpeg")


@app.get("/api/actions")
async def actions() -> dict:
    """The action vocabulary for the dashboard's Actions modal.

    Read straight from the registry and config, so the modal never drifts from
    what the policy layer actually allows."""
    from controller.actions.registry import REGISTRY
    from controller.main import load_config

    config = load_config()
    threshold = config.get("min_confidence")  # global override, may be None

    def reverse(section: str) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for trigger, spec in (config.get(section) or {}).items():
            out.setdefault(spec["action"], []).append(trigger)
        return out

    gestures, keys = reverse("gestures"), reverse("keyboard")
    keep = ("type", "default", "minimum", "maximum", "pattern", "minLength")

    items = []
    for spec in REGISTRY.values():
        props = spec.param_model.model_json_schema().get("properties", {})
        items.append({
            "name": spec.name,
            "description": spec.description,
            "min_confidence": threshold if threshold is not None else spec.min_confidence,
            "destructive": spec.destructive,
            "platforms": sorted(spec.supported_platforms),
            "parameters": [{"name": n, **{k: v for k, v in p.items() if k in keep}}
                           for n, p in props.items()],
            "gestures": gestures.get(spec.name, []),
            "keys": keys.get(spec.name, []),
        })
    return {"threshold": threshold, "actions": items}


@app.get("/api/gesture-mappings")
async def gesture_mappings() -> dict:
    from controller.actions.registry import REGISTRY
    from controller.inputs.gesture_labels import MODEL_LABELS
    from controller.main import load_config

    config = load_config()
    current = {
        name: spec.get("action")
        for name, spec in (config.get("gestures") or {}).items()
        if name != "open_palm"
    }
    names = list(dict.fromkeys([
        "swipe_left", "swipe_right", "swipe_up", "swipe_down",
        *MODEL_LABELS.values(),
        *current.keys(),
    ]))
    return {
        "mappings": [{"gesture": name, "action": current.get(name)} for name in names],
        "actions": [
            {"name": spec.name, "description": spec.description}
            for spec in REGISTRY.values()
        ],
    }


@app.put("/api/gesture-mappings")
async def update_gesture_mappings(request: GestureMappingRequest) -> dict:
    from controller.actions.registry import REGISTRY
    from controller.inputs.gesture_labels import MODEL_LABELS
    from controller.main import CONFIG_PATH, load_config

    known = {
        "swipe_left", "swipe_right", "swipe_up", "swipe_down",
        *MODEL_LABELS.values(),
    }
    unknown_gestures = set(request.mappings) - known
    if unknown_gestures:
        return {"ok": False, "error": f"unknown gestures: {sorted(unknown_gestures)}"}
    invalid_actions = {
        action for action in request.mappings.values()
        if action and action not in REGISTRY
    }
    if invalid_actions:
        return {"ok": False, "error": f"unknown actions: {sorted(invalid_actions)}"}

    config = load_config()
    mappings = {
        gesture: {"action": action}
        for gesture, action in request.mappings.items()
        if action
    }
    config["gestures"] = mappings
    import yaml

    existing_text = CONFIG_PATH.read_text()
    gesture_block = yaml.safe_dump({"gestures": mappings}, sort_keys=False).rstrip()
    pattern = r"(?ms)^gestures:\n.*?(?=^# Keyboard key)"
    if not re.search(pattern, existing_text):
        return {"ok": False, "error": "could not locate the gestures section"}
    updated_text = re.sub(
        pattern,
        f"{gesture_block}\n\n",
        existing_text,
    )
    yaml.safe_load(updated_text)
    temporary_fd, temporary_name = tempfile.mkstemp(
        prefix=f".{CONFIG_PATH.name}.", suffix=".tmp", dir=CONFIG_PATH.parent
    )
    try:
        with os.fdopen(temporary_fd, "w") as temporary_file:
            temporary_file.write(updated_text)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_name, CONFIG_PATH)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise

    pipeline = _voice_pipeline
    if pipeline is not None:
        from controller.decision.composite import CompositeEngine
        from controller.decision.rules import RuleBasedEngine

        engines = (
            pipeline.engine.engines
            if isinstance(pipeline.engine, CompositeEngine)
            else [pipeline.engine]
        )
        for engine in engines:
            if isinstance(engine, RuleBasedEngine):
                engine.update_gesture_map({
                    gesture: action for gesture, action in request.mappings.items() if action
                })
                break
    return {"ok": True, "mappings": config["gestures"]}


@app.post("/api/confirm")
async def confirm_action(request: ConfirmationRequest) -> dict:
    pipeline = _get_voice_pipeline()
    result = await asyncio.to_thread(pipeline.confirm_pending, request.confirmed)
    entry = dict(_latest)
    if entry:
        _history.append(entry)
        await _broadcast(entry)
    return {"ok": result.status in {"success", "cancelled"}, "status": result.status,
            "detail": result.detail}


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
_always_on_source = None
_always_on_thread: threading.Thread | None = None
_always_on_stop = threading.Event()
_always_on_ready = threading.Event()
_always_on_error: str | None = None
_gesture_stop = threading.Event()
_voice_queue: asyncio.Queue | None = None
_voice_consumer_task: asyncio.Task | None = None


def _voice_observer(entry: dict) -> None:
    _latest.clear()
    _latest.update(entry)
    if entry.get("timings_ms"):
        _metrics.append(entry["timings_ms"])


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
            PolicyEngine(
                platform=controller.platform,
                min_confidence=config.get("min_confidence"),
                confidence_overrides=config.get("gesture_confidence"),
            ),
            controller, AuditLog(stream=None), observer=_voice_observer,
        )
        _voice_pipeline.confirmation_timeout_seconds = float(
            config.get("confirmation_timeout_seconds", 30.0)
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


async def _handle_voice_event(event: VoiceEvent) -> None:
    _set_runtime("pipeline", state="running", error=None)
    try:
        await asyncio.wait_for(
            asyncio.to_thread(_get_voice_pipeline().handle, event),
            timeout=float(os.environ.get("ORCUS_COMMAND_TIMEOUT", "30")),
        )
    except Exception:
        _set_runtime("pipeline", state="error", error="voice command timed out or failed")
        raise
    finally:
        _set_runtime("pipeline", state="idle")
    entry = dict(_latest)
    _history.append(entry)
    await _broadcast(entry)


async def _voice_command_consumer(queue: asyncio.Queue) -> None:
    while True:
        event = await queue.get()
        try:
            await _handle_voice_event(event)
        except Exception as error:
            _set_runtime("voice", state="error", error=str(error))
        finally:
            queue.task_done()


def _ensure_voice_consumer() -> None:
    """Create the voice queue + consumer on the running loop if missing. Needed
    because always-on can be started by the UI button, not just ORCUS_ALWAYS_ON."""
    global _voice_queue, _voice_consumer_task
    if _voice_queue is None:
        _voice_queue = asyncio.Queue(maxsize=8)
    if _voice_consumer_task is None or _voice_consumer_task.done():
        _voice_consumer_task = asyncio.create_task(_voice_command_consumer(_voice_queue))


def _enqueue_voice_event(event: VoiceEvent) -> None:
    if _voice_queue is None:
        return
    try:
        _voice_queue.put_nowait(event)
    except asyncio.QueueFull:
        _set_runtime("voice", state="error", error="voice command queue is full")


def _always_on_worker(loop: asyncio.AbstractEventLoop) -> None:
    from controller.inputs.voice import AlwaysOnVoiceInput

    global _always_on_source, _always_on_error
    while not _always_on_stop.is_set():
        try:
            source = AlwaysOnVoiceInput(
                _get_recognizer(),
                wake_phrases=(os.environ.get("ORCUS_WAKE_WORD", "computer"),),
                on_status=lambda message: print(f"voice: {message}", flush=True),
            )
            _always_on_source = source
            _set_runtime("voice", state="running", error=None)
            _always_on_ready.set()
            for event in source.events():
                if _always_on_stop.is_set():
                    break
                loop.call_soon_threadsafe(_enqueue_voice_event, event)
        except Exception as error:
            _always_on_error = str(error)
            _set_runtime("voice", state="error", error=str(error))
            _always_on_ready.set()
            print(f"voice: retrying after error: {error}", flush=True)
            _always_on_stop.wait(2.0)
        finally:
            _always_on_source = None
    _set_runtime("voice", state="stopped", error=None)


@app.get("/api/voice/always-on")
async def always_on_status() -> dict:
    return {"active": _always_on_thread is not None and _always_on_thread.is_alive(),
            "wake_word": os.environ.get("ORCUS_WAKE_WORD", "computer"),
            "error": _always_on_error}


@app.post("/api/voice/always-on/start")
async def always_on_start() -> dict:
    global _always_on_thread, _always_on_error
    if _always_on_thread is not None and _always_on_thread.is_alive():
        return await always_on_status()
    try:
        _get_recognizer()
    except RuntimeError as error:
        _set_runtime("voice", state="error", error=str(error))
        return {"active": False, "error": str(error)}
    _ensure_voice_consumer()  # so button-started always-on actually runs commands
    _always_on_stop.clear()
    _always_on_ready.clear()
    _always_on_error = None
    loop = asyncio.get_running_loop()
    _always_on_thread = threading.Thread(
        target=_always_on_worker, args=(loop,), daemon=True, name="orcus-always-on-voice",
    )
    _always_on_thread.start()
    await asyncio.to_thread(_always_on_ready.wait, 1.0)
    return await always_on_status()


@app.post("/api/voice/always-on/stop")
async def always_on_stop() -> dict:
    _always_on_stop.set()
    if _always_on_source is not None:
        _always_on_source.stop()
    _set_runtime("voice", state="stopping")
    return {"active": False}


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
