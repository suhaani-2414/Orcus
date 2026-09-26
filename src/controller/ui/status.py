"""Live status dashboard (Textual).

Shows the pipeline in real time: platform, last input, the decision + its
confidence, and the execution result — the OUTLINE's UI mockup.

  Step 1: static layout.
  Step 2: show_event() populates the panels with color coding.
  Step 3: live — the real pipeline drives the panels as events flow (this file).
"""

from __future__ import annotations

import asyncio

from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.widgets import Footer, Header, ProgressBar, Static

from controller.decision.schemas import GestureEvent, KeyboardEvent, VoiceEvent

# Confidence at/above this reads as "would pass policy" in the UI.
PASS_THRESHOLD = 0.70

_EXEC_COLOR = {"success": "green", "error": "red", "unsupported": "yellow", "skipped": "grey62"}
_INPUT_ICON = {"voice": "🎤", "gesture": "✋", "keyboard": "⌨"}

# Scripted events for the live demo — one of each modality, plus a low-confidence
# gesture (policy-denied) and unmapped speech (no intent) to show the failure states.
_DEMO_EVENTS = [
    VoiceEvent(text="switch to workspace three"),
    GestureEvent(name="swipe_right", confidence=0.95),
    VoiceEvent(text="volume up"),
    KeyboardEvent(key="MEDIA_PLAY_PAUSE"),
    GestureEvent(name="swipe_left", confidence=0.30),  # below threshold -> denied
    VoiceEvent(text="do a barrel roll"),               # unmapped -> no intent
]


def _raw_text(raw_input: dict) -> str:
    """Human-readable form of a normalized event for the Last Input panel."""
    if raw_input.get("type") == "voice":
        return raw_input.get("text", "")
    if raw_input.get("type") == "gesture":
        return raw_input.get("name", "")
    if raw_input.get("type") == "keyboard":
        return raw_input.get("key", "")
    return str(raw_input)


class StatusApp(App):
    TITLE = "Multimodal OS Controller"

    CSS = """
    Screen { align: center middle; }

    #body {
        width: 72;
        height: auto;
        border: round $accent;
        padding: 1 2;
    }

    #platform { color: $text-muted; margin-bottom: 1; }

    .section-title {
        text-style: bold;
        color: $accent;
        margin-top: 1;
    }

    #last-input, #decision, #confidence-note, #execution { margin-left: 2; }
    #confidence { margin-left: 2; margin-top: 1; }
    """

    def __init__(self, demo: bool = False):
        super().__init__()
        self._demo = demo

    def on_mount(self) -> None:
        if self._demo:
            self.run_worker(self._run_demo(), exclusive=True)

    async def _run_demo(self) -> None:
        """Replay scripted events through the REAL pipeline, one every ~1.6s."""
        from controller.audit.log import AuditLog
        from controller.main import build_rule_engine, load_config
        from controller.os.base import ExecutionResult, OSController
        from controller.pipeline import Pipeline
        from controller.policy.validator import PolicyEngine

        class DryRun(OSController):
            platform = "linux"

            def execute(self, intent):
                return ExecutionResult(status="success", detail="[dry-run]")

        engine = build_rule_engine(load_config())
        pipeline = Pipeline(
            engine, PolicyEngine(platform="linux"), DryRun(),
            AuditLog(stream=None), observer=self._on_entry,  # no stdout: it'd corrupt the TUI
        )
        await asyncio.sleep(0.8)
        while True:
            for event in _DEMO_EVENTS:
                pipeline.handle(event)  # observer -> show_event, synchronously on this loop
                await asyncio.sleep(1.6)

    def _on_entry(self, entry: dict) -> None:
        """Adapt a pipeline audit entry to show_event."""
        self.show_event(
            platform=entry["platform"],
            input_type=entry["input_type"],
            raw=_raw_text(entry["raw_input"]),
            action=entry["decision"],
            confidence=entry["confidence"],
            execution=entry["execution"],
        )

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="body"):
            yield Static("Platform: —    Status: Idle", id="platform")
            yield Static("Last Input", classes="section-title")
            yield Static("(waiting…)", id="last-input")
            yield Static("Decision", classes="section-title")
            yield Static("—", id="decision")
            yield ProgressBar(id="confidence", total=100, show_eta=False)
            yield Static("", id="confidence-note")
            yield Static("Execution", classes="section-title")
            yield Static("—", id="execution")
        yield Footer()

    def show_event(
        self,
        *,
        platform: str,
        input_type: str,
        raw: str,
        action: str | None,
        confidence: float | None,
        execution: str,
    ) -> None:
        """Update every panel from one pipeline step. Safe to call repeatedly."""
        self.query_one("#platform", Static).update(
            f"Platform: {platform}    Status: [green]Listening[/]"
        )
        icon = _INPUT_ICON.get(input_type, "•")
        self.query_one("#last-input", Static).update(f'{icon} [{input_type}]  "{raw}"')

        self.query_one("#decision", Static).update(
            f"[b]{action}[/]" if action else "[grey62]— (no intent)[/]"
        )

        pct = round((confidence or 0.0) * 100)
        self.query_one("#confidence", ProgressBar).update(progress=pct)
        if confidence is None:
            note = ""
        elif confidence >= PASS_THRESHOLD:
            note = f"[green]confidence {pct}%  ✓ above threshold[/]"
        else:
            note = f"[red]confidence {pct}%  ✗ below {int(PASS_THRESHOLD*100)}%[/]"
        self.query_one("#confidence-note", Static).update(note)

        color = _EXEC_COLOR.get(execution, "white")
        self.query_one("#execution", Static).update(f"[{color}]{execution}[/]")


if __name__ == "__main__":
    StatusApp(demo=True).run()
