# Tech Stack — Multimodal OS Controller

> **Recommended** picks filled in for a Linux/Hyprland hackathon build.
> Gestures = hero modality, voice = secondary, keyboard = silent fallback.
> Anything you'd rather swap, just override.

---

## Input Layer

| Concern | Tool | Notes |
|---|---|---|
| Voice / Speech-to-Text | **ElevenLabs** (Scribe STT) | ⚠️ Cloud/online — clashes with "local-first". Keep **faster-whisper** (local) as fallback so a dead wifi doesn't kill the demo. |
| Hand gesture recognition | **MediaPipe Hands** | 21 hand landmarks, local, no training. Your hero. |
| Camera capture | **OpenCV** (`opencv-python`) | Grabs webcam frames → feeds MediaPipe. |
| Keyboard / mouse events | **pynput** (or `evdev`) | pynput = cross-platform + simpler. Your fallback trigger path. |
| Wake word / push-to-talk | **Push-to-talk (keybind)** | Skip wake-word. Hold a key to listen — deterministic, no false triggers on stage. |

## Decision Layer ("Laya")

| Concern | Tool | Notes |
|---|---|---|
| Intent engine | **Rule/keyword grammar first** | Deterministic, instant, never embarrasses you live. |
| Model / runtime (optional upgrade) | **Claude API** (Haiku) | Only for free-form voice → intent *if* you have time. Keep rules as fallback. |
| Intent schema / validation | **Pydantic v2** | Strongly-typed intents = the outline's core requirement. |

## Policy / Safety Layer

| Concern | Tool | Notes |
|---|---|---|
| Schema validation | **Pydantic** | Same models as above; reject malformed intents. |
| Confidence + permission rules | **Custom Python** | Small module: confidence threshold, action allowlist, confirm destructive. |

## OS Adapter Layer (Linux — primary)

| Concern | Tool | Notes |
|---|---|---|
| Window manager / workspaces | **`hyprctl`** via subprocess | Or Hyprland IPC socket. subprocess is faster to build. |
| Audio / volume | **`wpctl`** (WirePlumber/PipeWire) | Already on your Arch box. |
| Media control | **`playerctl`** | play/pause/next across MPRIS players. |
| App launching | **subprocess** + `.desktop` lookup | `subprocess.Popen` on resolved binary. |
| System (lock, etc.) | **`loginctl` / D-Bus** | `loginctl lock-session`. |

## OS Adapter Layer (macOS — deferred)

| Concern | Tool | Notes |
|---|---|---|
| Everything | **Stub / NotImplemented** | Keep the interface, raise `unsupported`. Say "drop-in adapter" in pitch. |

## Core / Runtime

| Concern | Tool | Notes |
|---|---|---|
| Language | **Python 3.11+** | MediaPipe + ecosystem all Python. |
| Package / env manager | **uv** | Fastest; instant `uv venv` + `uv pip`. |
| Config format | **YAML** (`pyyaml`) | Gesture→action mappings live here. |
| Async / event loop | **asyncio** | Inputs run concurrently → one event queue → decision loop. |

## UI / Feedback

| Concern | Tool | Notes |
|---|---|---|
| Status dashboard | **Textual** (or Rich) | Your demo secret weapon — live input→intent→confidence→execution panel. TUI = zero browser setup. |
| Voice feedback (TTS) | **ElevenLabs TTS** | Reuse your ElevenLabs key for spoken confirmations ("Workspace three"). Nice wow, optional. |

## Observability

| Concern | Tool | Notes |
|---|---|---|
| Structured logging / audit | **stdlib `logging`** → JSON lines | Matches the outline's audit-record spec. `structlog` if you want it prettier. |

## Dev / Ops

| Concern | Tool | Notes |
|---|---|---|
| Testing | **pytest** | Platform-independent tests run anywhere; guard Linux tests with a skip. |
| Linting / formatting | **ruff** | Format + lint in one tool. |
| Version control | **git** | Repo not initialized yet — `git init` when you start. |
| Demo backup | **OBS screen recording** | Record a clean successful run as insurance. |

## hackUMBC Sponsor Integrations

Ranked by realistic fit. Anchor on the top three (synergistic + low effort);
DigitalOcean is the reach. Skip the rest — forcing them makes the build incoherent.

| Sponsor | Prize | Fit | How it plugs into OUR architecture | Effort |
|---|---|---|---|---|
| **ElevenLabs** ★★★ | Wireless earbuds | Core | STT (Scribe, decided) **+ TTS spoken confirmations** ("Workspace three") | Low — already the voice layer |
| **Tiger Data** ★★★ | Stream Deck Mini | Excellent | `audit/log.py` already emits timestamped events → add a Tiger Data sink → **live analytics dashboard** (commands/min, confidence distribution, modality split, latency). This IS our demo UI. | Low–Med |
| **GoDaddy Registry** ★★★ | Gift card | Free win | Register a domain (e.g. `laya-control.tech`). No code. | ~5 min |
| **DigitalOcean** ★★ | Retro mouse | Reach | Host dashboard/API on a Droplet; **or Gradient GPU for a full Laya fine-tune** (solves our local GPU gap) | Med |
| **Backboard** ★★ | Tile pack | Plausible | Persistent user memory: frequent commands, per-app prefs, custom gesture maps across sessions ("learns routines" = their own example) | Med |
| **Gemini** ★ | Swag kit | Stretch | Fallback for complex/ambiguous voice Laya can't classify (decompose "open email and mute" → multiple intents). Competes with Laya — judges will ask why both. | Med |
| **Snowflake** ✗ | Raspberry Pi 4 | Skip | Redundant with Tiger Data (analytics) + Gemini (LLM) | — |
| **Solana** ✗ | Ledger Nano | Skip | No genuine fit; on-chain audit log is a gimmick | — |

**Winning narrative:** *local-first multimodal OS control, decided by Laya, voiced by ElevenLabs, observed via Tiger Data.* Three tightly-integrated sponsors beat eight bolted-on logos.

Sponsor deps to add when building those integrations:
```bash
uv pip install elevenlabs psycopg[binary]   # ElevenLabs TTS + Tiger Data (Postgres wire protocol)
```

---

## Install (one shot)

```bash
uv venv && source .venv/bin/activate
uv pip install mediapipe opencv-python pynput pydantic pyyaml textual rich pytest ruff faster-whisper elevenlabs
```

System tools (already on Arch/Hyprland, verify): `hyprctl`, `wpctl`, `playerctl`, `loginctl`.

## Resolve before coding
1. **ElevenLabs STT vs local whisper** — pick primary, keep the other as fallback.
2. **Laya = rules or LLM** — start rules; add Claude only if time allows.
