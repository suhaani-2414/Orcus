"""Voice input via ElevenLabs Scribe STT.

Pipeline:  mic → short WAV recording → Scribe (speech-to-text) → VoiceEvent → Laya.

Per the OUTLINE, the speech layer only produces text — it never executes anything.
SpeechRecognizer is a replaceable interface; ScribeRecognizer is the ElevenLabs
implementation. Recording uses a system tool (arecord/ffmpeg) so there's no
PortAudio/PyAudio system dependency. The elevenlabs import is lazy so this module
loads without the SDK or an API key present (tests use a fake recognizer).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Iterator

from controller.decision.schemas import Event, VoiceEvent
from controller.inputs.base import InputSource

MODEL_ID = "scribe_v1"


class SpeechRecognizer(ABC):
    @abstractmethod
    def listen(self) -> str:
        """Capture speech and return the transcribed text (may be empty)."""
        raise NotImplementedError


def _record_wav(path: str, seconds: float) -> None:
    """Record mono 16 kHz WAV using whatever recorder is available."""
    if shutil.which("arecord"):
        # arecord -d takes whole seconds only.
        cmd = ["arecord", "-q", "-d", str(round(seconds)), "-f", "S16_LE",
               "-r", "16000", "-c", "1", path]
    elif shutil.which("ffmpeg"):
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "pulse",
               "-i", "default", "-t", str(seconds), "-ar", "16000", "-ac", "1", "-y", path]
    else:
        raise RuntimeError("no mic recorder found (need arecord or ffmpeg)")
    subprocess.run(cmd, check=True)


class ScribeRecognizer(SpeechRecognizer):
    def __init__(self, api_key: str | None = None, record_seconds: float = 4.0,
                 language_code: str = "en"):
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY")
        if not self.api_key:
            raise RuntimeError("set ELEVENLABS_API_KEY (your promo credits) to use voice input")
        self.record_seconds = record_seconds
        self.language_code = language_code
        self._client = None

    def _get_client(self):
        if self._client is None:
            from elevenlabs.client import ElevenLabs

            self._client = ElevenLabs(api_key=self.api_key)
        return self._client

    def transcribe(self, wav_path: str) -> str:
        """Send an existing WAV to Scribe and return the text."""
        with open(wav_path, "rb") as f:
            result = self._get_client().speech_to_text.convert(
                model_id=MODEL_ID, file=f, language_code=self.language_code,
            )
        return (getattr(result, "text", "") or "").strip()

    def warm(self) -> None:
        """Instantiate the client ahead of time so the first real call doesn't
        pay client/TLS setup. Best-effort."""
        try:
            self._get_client()
        except Exception:
            pass

    def listen(self) -> str:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            _record_wav(tmp.name, self.record_seconds)
            return self.transcribe(tmp.name)


class MicRecorder:
    """Start/stop mic recording for hold-to-talk: records until stopped, so the
    clip is only as long as you speak (shorter clip = faster upload + STT)."""

    def __init__(self):
        self._proc: subprocess.Popen | None = None
        self._path: str | None = None

    def start(self) -> None:
        if self._proc is not None:
            return
        self._path = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        if shutil.which("arecord"):
            cmd = ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", self._path]
        elif shutil.which("ffmpeg"):
            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "pulse",
                   "-i", "default", "-ar", "16000", "-ac", "1", "-y", self._path]
        else:
            raise RuntimeError("no mic recorder found (need arecord or ffmpeg)")
        self._proc = subprocess.Popen(cmd)

    def stop(self) -> str | None:
        """Stop recording; return the WAV path (or None if not recording)."""
        if self._proc is None:
            return None
        self._proc.terminate()
        try:
            self._proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait()
        self._proc = None
        path, self._path = self._path, None
        return path


class VoiceInput(InputSource):
    """Push-to-talk voice source: Enter to record a clip, Scribe transcribes it."""

    def __init__(self, recognizer: SpeechRecognizer, prompt: bool = True):
        self.recognizer = recognizer
        self.prompt = prompt
        self._running = False

    def stop(self) -> None:
        self._running = False

    def events(self) -> Iterator[Event]:
        self._running = True
        while self._running:
            if self.prompt:
                try:
                    input("\n🎤 Press Enter to speak (Ctrl+C to quit)…")
                except (EOFError, KeyboardInterrupt):
                    break
            text = self.recognizer.listen()
            if text:
                print(f'   heard: "{text}"')
                yield VoiceEvent(text=text)
            else:
                print("   (nothing transcribed)")
