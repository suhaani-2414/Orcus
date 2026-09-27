"""Entry point. Stage 1: run the vertical slice with mocked input.

  python -m controller.main            # dry-run demo (no real OS actions)
  python -m controller.main --execute  # actually execute on this machine

The demo feeds mock voice/gesture/keyboard events through the full pipeline.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from controller.audit.log import AuditLog
from controller.config import load_env_file
from controller.decision.rules import RuleBasedEngine
from controller.decision.schemas import GestureEvent, KeyboardEvent, VoiceEvent
from controller.inputs.mock import MockInput
from controller.os.base import ExecutionResult, OSController
from controller.os.factory import get_os_controller
from controller.os.platform import detect_linux_wm, detect_platform
from controller.pipeline import Pipeline
from controller.policy.validator import PolicyEngine

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.yaml"


def load_config() -> dict:
    with CONFIG_PATH.open() as f:
        return yaml.safe_load(f)


def build_rule_engine(config: dict) -> RuleBasedEngine:
    gesture_map = {name: spec["action"] for name, spec in config.get("gestures", {}).items()}
    keyboard_map = {key: spec["action"] for key, spec in config.get("keyboard", {}).items()}
    return RuleBasedEngine(gesture_map=gesture_map, keyboard_map=keyboard_map)


def build_engine(config: dict, use_laya: bool):
    """Rules by default. With Laya: voice -> Laya, gesture/keyboard -> rules,
    and rules also back up any voice Laya declines."""
    rules = build_rule_engine(config)
    if not use_laya:
        return rules

    import os

    from controller.actions.registry import LAYA_TRAINED_ACTIONS
    from controller.decision.composite import CompositeEngine
    from controller.decision.laya import LayaDecisionEngine
    from controller.decision.laya_loader import FINETUNED_DIR, load_laya_client
    from controller.decision.web_commands import WebCommandEngine

    # The fine-tuned checkpoint learned to abstain, so it can use the "none"
    # option; the zero-shot base over-picks "none", so it relies on the policy
    # confidence threshold instead. Pin Laya to its trained 15-action set so
    # registry extras (web_search, open_url) don't disturb its calibration.
    finetuned = (FINETUNED_DIR / "model.safetensors").exists()
    print(f"Loading Laya ({'fine-tuned' if finetuned else 'base'})...")
    laya = LayaDecisionEngine(
        load_laya_client(), actions=LAYA_TRAINED_ACTIONS, allow_none=finetuned
    )

    from controller.sites import SiteStore

    # One Gemini instance serves both URL resolution (learn new sites) and the
    # natural-language fallback.
    gemini = None
    if os.environ.get("GEMINI_API_KEY"):
        from controller.decision.gemini import GeminiDecisionEngine

        gemini = GeminiDecisionEngine()
        print("Gemini fallback: on")

    web = WebCommandEngine(
        sites=SiteStore(), resolver=(gemini.resolve_url if gemini else None)
    )

    # Order = speed: exact web commands -> deterministic common commands ->
    # Laya for natural language -> optional Gemini fallback.
    engines = [web, rules, laya]
    if gemini is not None:
        engines.append(gemini)
    return CompositeEngine(engines)


class DryRunController(OSController):
    """Reports what a real controller would do, without touching the OS."""

    def __init__(self, platform: str):
        self.platform = platform

    def execute(self, intent):  # noqa: ANN001
        return ExecutionResult(status="success", detail=f"[dry-run] {intent.action} {intent.parameters}")


def main() -> None:
    load_env_file()
    parser = argparse.ArgumentParser(description="Multimodal OS Controller (Stage 1)")
    parser.add_argument("--execute", action="store_true", help="run real OS actions")
    parser.add_argument(
        "--input", choices=["demo", "gesture", "voice", "always-on"], default="demo",
        help="demo = replay mock events; gesture = live webcam swipes; "
        "voice = ElevenLabs Scribe push-to-talk; always-on = wake-word listening",
    )
    parser.add_argument(
        "--wake-word", default="Orcus",
        help="wake phrase for always-on voice mode (default: Orcus)",
    )
    parser.add_argument(
        "--engine", choices=["rules", "laya"], default="rules",
        help="rules = keyword/config engine; laya = Laya for voice + rules fallback",
    )
    args = parser.parse_args()

    config = load_config()
    platform = detect_platform()
    wm = detect_linux_wm() if platform == "linux" else None

    controller: OSController = (
        get_os_controller(platform) if args.execute else DryRunController(platform)
    )

    engine = build_engine(config, use_laya=args.engine == "laya")
    policy = PolicyEngine(platform=platform, min_confidence=config.get("min_confidence"))
    audit = AuditLog()  # stdout
    pipeline = Pipeline(engine, policy, controller, audit)

    print(f"Platform: {platform}" + (f" / {wm}" if wm else ""))
    print(f"Mode: {'EXECUTE' if args.execute else 'dry-run'} | Input: {args.input}\n")

    if args.input == "gesture":
        from controller.inputs.gestures import GestureInput

        print("Swipe left/right to change workspace. Press q in the window to quit.\n")
        source = GestureInput()
    elif args.input == "voice":
        from controller.inputs.voice import ScribeRecognizer, VoiceInput

        print("Voice mode (ElevenLabs Scribe). Speak a command after pressing Enter.\n")
        source = VoiceInput(ScribeRecognizer())
    elif args.input == "always-on":
        from controller.inputs.voice import AlwaysOnVoiceInput, ScribeRecognizer

        print(f"Always-on voice mode. Say '{args.wake_word} <command>'. Press Ctrl+C to quit.\n")
        source = AlwaysOnVoiceInput(
            ScribeRecognizer(),
            wake_phrases=(args.wake_word,),
            on_status=lambda message: print(f"   {message}", flush=True),
        )
    else:
        # The OUTLINE's first vertical slice, plus one of each other modality.
        source = MockInput([
            VoiceEvent(text="switch to workspace three"),
            VoiceEvent(text="volume up"),
            GestureEvent(name="swipe_right", confidence=0.95),
            KeyboardEvent(key="MEDIA_PLAY_PAUSE"),
            VoiceEvent(text="do a barrel roll"),  # unmapped -> no intent
        ])

    try:
        for event in source.events():
            result = pipeline.handle(event)
            if result.status == "confirmation_required":
                try:
                    answer = input(f"{result.detail}. Proceed? [y/N] ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    answer = ""
                pipeline.confirm_pending(answer in {"y", "yes"})
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
