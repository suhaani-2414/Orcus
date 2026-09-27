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
import re
import shutil
import subprocess
import tempfile
import time
import wave
from array import array
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

    def synthesize(self, text: str, voice_id: str | None = None) -> bytes:
        """Return ElevenLabs MP3 audio for optional spoken dashboard feedback."""
        if not text.strip():
            return b""
        result = self._get_client().text_to_speech.convert(
            voice_id=voice_id or os.environ.get(
                "ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"
            ),
            model_id=os.environ.get("ELEVENLABS_TTS_MODEL", "eleven_multilingual_v2"),
            output_format="mp3_44100_128",
            text=text,
        )
        if isinstance(result, bytes):
            return result
        return b"".join(result)

    def listen(self) -> str:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            _record_wav(tmp.name, self.record_seconds)
            return self.transcribe(tmp.name)

    def listen_chunk(self, seconds: float = 2.0) -> str:
        """Record one short always-on window and transcribe it."""
        path = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        try:
            _record_wav(path, seconds)
            if not _wav_has_audio(path):
                return ""
            return self.transcribe(path)
        finally:
            try:
                os.remove(path)
            except OSError:
                pass


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


def _wav_has_audio(path: str, threshold: int = 250) -> bool:
    """Return whether a mono PCM WAV has enough energy to upload."""
    try:
        with wave.open(path, "rb") as wav:
            while True:
                frames = wav.readframes(4096)
                if not frames:
                    return False
                samples = array("h")
                samples.frombytes(frames[: len(frames) - (len(frames) % 2)])
                if samples and max(abs(sample) for sample in samples) >= threshold:
                    return True
    except (OSError, EOFError, wave.Error):
        return False


class AlwaysOnVoiceInput(InputSource):
    """Continuously listen for a wake phrase, then yield voice commands.

    The recognizer must expose ``listen_chunk(seconds)``. Audio is never sent
    to STT when the local RMS check detects silence. A command can be spoken as
    ``"Orcus volume up"`` or in two steps: ``"Orcus"`` followed by the command
    within ``activation_timeout`` seconds.
    """

    def __init__(
        self,
        recognizer,
        *,
        wake_phrases: tuple[str, ...] = ("computer", "hey computer"),
        chunk_seconds: float = 4.0,  # fit "computer <command>" in one window
        activation_timeout: float = 8.0,
        on_status=None,
    ):
        if chunk_seconds <= 0:
            raise ValueError("chunk_seconds must be positive")
        if not wake_phrases or any(not phrase.strip() for phrase in wake_phrases):
            raise ValueError("wake_phrases must contain non-empty phrases")
        self.recognizer = recognizer
        self.wake_phrases = tuple(phrase.strip().lower() for phrase in wake_phrases)
        self.chunk_seconds = chunk_seconds
        self.activation_timeout = activation_timeout
        self.on_status = on_status or (lambda _message: None)
        self._running = False
        self._active_until = 0.0

    def stop(self) -> None:
        self._running = False

    def _strip_wake_phrase(self, text: str) -> str | None:
        normalized = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        for phrase in sorted(self.wake_phrases, key=len, reverse=True):
            if normalized == phrase:
                return ""
            if normalized.startswith(phrase + " "):
                return normalized[len(phrase):].strip()
        if "orcus" in self.wake_phrases:
            for variant in ("orcas", "orkus", "orcus", "orcuss", "ocus", "orcos"):
                if normalized == variant:
                    return ""
                if normalized.startswith(variant + " "):
                    return normalized[len(variant):].strip()
        return None

    def events(self) -> Iterator[Event]:
        self._running = True
        self.on_status(f"always-on listening; say {self.wake_phrases[0]!r}")
        while self._running:
            try:
                text = self.recognizer.listen_chunk(self.chunk_seconds).strip()
            except Exception as error:
                self.on_status(f"voice retrying after error: {error}")
                time.sleep(0.5)
                continue
            if not text:
                continue

            now = time.monotonic()
            command = self._strip_wake_phrase(text)
            if command is not None:
                self._active_until = now + self.activation_timeout
                if command:
                    self.on_status(f"heard command: {command!r}")
                    yield VoiceEvent(text=command)
                else:
                    self.on_status("activated; listening for a command")
                continue

            if now <= self._active_until:
                self._active_until = 0.0
                self.on_status(f"heard command: {text!r}")
                yield VoiceEvent(text=text)
            else:
                # Show what STT heard so a mis-transcribed wake word is visible.
                self.on_status(f"ignored (say wake word first): {text!r}")
