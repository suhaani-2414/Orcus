"""Generate a domain dataset: voice utterances -> action label.

Templated paraphrases across the 15-action registry plus 'none' (unrelated
speech), so fine-tuning teaches Laya both the right action AND when to abstain.
Writes JSONL {"text", "action"} and a train/eval split.

    python training/generate_dataset.py
"""

from __future__ import annotations

import json
import random
from pathlib import Path

random.seed(7)

OUT = Path(__file__).resolve().parent / "data"

APPS = [
    "firefox", "chrome", "the terminal", "kitty", "spotify", "vs code",
    "the file manager", "discord", "slack", "obsidian", "blender", "steam",
    "the browser", "the music player",
]

# action -> list of surface forms. {n} filled with a workspace number, {app} with APPS.
TEMPLATES: dict[str, list[str]] = {
    "open_app": [
        "open {app}", "launch {app}", "start {app}", "fire up {app}",
        "can you open {app}", "please launch {app}", "open up {app}",
        "run {app}", "bring up {app}", "get {app} going", "start up {app}",
    ],
    "switch_workspace": [
        "switch to workspace {n}", "go to workspace {n}", "workspace {n}",
        "take me to workspace {n}", "move to desktop {n}", "switch to desktop {n}",
        "jump to workspace {n}", "show workspace {n}", "go to desktop {n}",
    ],
    "next_workspace": [
        "next workspace", "go to the next workspace", "move to the next desktop",
        "switch to the next workspace", "workspace to the right", "next desktop please",
        "flip to the next workspace",
    ],
    "previous_workspace": [
        "previous workspace", "go back a workspace", "previous desktop",
        "workspace to the left", "go to the last workspace",
        "switch to the previous workspace", "back one workspace",
    ],
    "play_pause": [
        "play", "pause", "play the music", "pause the music", "toggle playback",
        "play the song", "pause the video", "resume playback", "hit play",
        "pause it", "play it", "resume the music",
    ],
    "next_track": [
        "next track", "next song", "skip this song", "skip track",
        "play the next song", "go to the next track", "skip forward", "next tune",
    ],
    "previous_track": [
        "previous track", "previous song", "go back a song",
        "play the previous track", "last song", "back a track", "replay the previous song",
    ],
    "volume_up": [
        "volume up", "turn it up", "louder", "raise the volume",
        "increase the volume", "turn the volume up", "crank it up",
        "bump the volume", "make it louder", "pump up the volume",
    ],
    "volume_down": [
        "volume down", "turn it down", "quieter", "lower the volume",
        "decrease the volume", "turn the volume down", "make it quieter",
        "bring the volume down", "soften the sound",
    ],
    "mute": [
        "mute", "unmute", "mute the sound", "mute it", "silence",
        "turn off the sound", "toggle mute", "mute the audio", "cut the sound",
    ],
    "lock_screen": [
        "lock the screen", "lock my screen", "lock the computer", "lock it",
        "lock my pc", "secure the screen", "lock the session", "screen lock",
    ],
    "close_app": [
        "close this", "close the app", "close the window", "quit this application",
        "close the current app", "shut this app", "exit the application", "close it",
    ],
    "focus_window": [
        "focus the window", "focus on this window", "bring this window to the front",
        "give focus to the window", "put focus on the window", "focus the active window",
        "raise this window",
    ],
    "move_window": [
        "move the window", "move this window", "move the window left",
        "move it to the other side", "reposition the window", "shift the window",
        "move the window to the right",
    ],
    "resize_window": [
        "resize the window", "make the window bigger", "make this window smaller",
        "resize it", "shrink the window", "enlarge the window", "make the window wider",
    ],
    "none": [
        "what's the weather today", "tell me a joke", "what time is it",
        "who won the game last night", "how are you doing", "set an alarm for 7 am",
        "what's two plus two", "send an email to john", "what's on my calendar",
        "translate hello to french", "define serendipity", "how tall is mount everest",
        "what's the capital of france", "remind me to call mom", "order a pizza",
        "search for pasta recipes", "read me the news", "what's my schedule tomorrow",
    ],
}

WORD_NUM = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]


def _fill(template: str) -> list[str]:
    out = []
    if "{app}" in template:
        for app in APPS:
            out.append(template.replace("{app}", app))
    elif "{n}" in template:
        for n in range(1, 10):
            out.append(template.replace("{n}", str(n)))
            out.append(template.replace("{n}", WORD_NUM[n - 1]))
    else:
        out.append(template)
    return out


def generate(per_action_cap: int = 60) -> list[dict]:
    rows: list[dict] = []
    for action, templates in TEMPLATES.items():
        variants: set[str] = set()
        for t in templates:
            variants.update(_fill(t))
        picked = list(variants)
        random.shuffle(picked)
        for text in picked[:per_action_cap]:
            rows.append({"text": text, "action": action})
    random.shuffle(rows)
    return rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = generate()

    # Stratified-ish split: 85/15 by shuffling (already shuffled).
    split = int(len(rows) * 0.85)
    train, evalset = rows[:split], rows[split:]

    (OUT / "commands.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    (OUT / "train.jsonl").write_text("\n".join(json.dumps(r) for r in train) + "\n")
    (OUT / "eval.jsonl").write_text("\n".join(json.dumps(r) for r in evalset) + "\n")

    from collections import Counter
    counts = Counter(r["action"] for r in rows)
    print(f"total={len(rows)} train={len(train)} eval={len(evalset)}")
    for a, c in sorted(counts.items()):
        print(f"  {a:20} {c}")


if __name__ == "__main__":
    main()
