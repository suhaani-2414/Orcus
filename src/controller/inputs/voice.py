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
        cmd = ["arecord", "-q", "-d", str(seconds), "-f", "S16_LE", "-r", "16000", "-c", "1", path]
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

    def listen(self) -> str:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            _record_wav(tmp.name, self.record_seconds)
            with open(tmp.name, "rb") as f:
                result = self._get_client().speech_to_text.convert(
                    model_id=MODEL_ID, file=f, language_code=self.language_code,
                )
        return (getattr(result, "text", "") or "").strip()


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
