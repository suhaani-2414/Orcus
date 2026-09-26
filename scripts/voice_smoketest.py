"""Quick check that ElevenLabs Scribe STT + your mic work.

Records a few seconds and prints the transcript — no pipeline, no Enter prompts.

    ELEVENLABS_API_KEY must be set in this shell.
    python scripts/voice_smoketest.py [seconds]
"""

import sys

from controller.inputs.voice import ScribeRecognizer

seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 4.0
rec = ScribeRecognizer(record_seconds=seconds)
print(f"🎤 Recording for {seconds:.0f}s — speak a command now (e.g. 'switch to workspace three')…")
text = rec.listen()
print(f'\n   transcript: "{text}"' if text else "\n   (nothing transcribed)")
