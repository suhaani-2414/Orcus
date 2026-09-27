# Orcus stabilization pass

This document records the reliability, recognition, and latency work completed
for the hackathon release. The changes are intentionally additive: existing
gesture mappings, voice controls, confirmation behavior, and dashboard event
fields remain compatible.

## Environment setup

Copy `.env.example` to `.env` before running voice features:

```bash
cp .env.example .env
# edit .env and add ELEVENLABS_API_KEY; add GEMINI_API_KEY if desired
orcus
```

Orcus loads `.env` from the repository root without overriding variables
already exported by the shell. `.env`, `.env.local`, and `.env.*.local` are
ignored by git. Empty keys are safe for dry-run, gesture-only, and dashboard
work; voice input/TTS reports a clear unavailable state until
`ELEVENLABS_API_KEY` is supplied.

## What changed

### Runtime reliability

1. **Single-instance startup**  
   `orcus` now uses a non-blocking lock at `/tmp/orcus.lock` in addition to the
   port check. A second launch opens the existing dashboard instead of starting
   another camera or microphone worker. The lock path can be overridden with
   `ORCUS_LOCK_FILE`.

2. **Worker health visibility**  
   `GET /api/status` reports camera, voice, pipeline, and model-preload state.
   The dashboard footer polls this endpoint and shows the current health in
   plain language.

3. **Camera recovery**  
   Camera startup failures are recorded, retried every two seconds, and no
   longer permanently kill gesture input after a temporary device conflict.
   Camera selection and tuning are read from `config/config.yaml`.

4. **Continuous voice resilience**  
   Always-on recognition feeds a bounded queue instead of waiting for every
   command to finish. Pipeline execution has a configurable
   `ORCUS_COMMAND_TIMEOUT` (30 seconds by default), and listener failures are
   retried without requiring a dashboard restart.

5. **Safer mapping writes**  
   Gesture mapping updates validate the complete YAML document, write to a
   temporary file in the same directory, flush it, `fsync` it, and replace the
   configuration atomically.

### Recognition controls

6. **Setup diagnostics**  
   `GET /api/setup` exposes safe first-run information: whether voice
   credentials are configured, execution mode, camera index, wake word, gesture
   tuning, and current worker health. Secrets are never returned.

7. **Per-gesture confidence**  
   `gesture_confidence` supports stricter thresholds for individual gesture
   names. The default configuration keeps `four_fingers` at a conservative
   0.75 threshold while preserving the global 0.50 gate.

8. **Configurable dead zone and cooldown**  
   `gesture_settings` now controls swipe minimum travel and cooldown, plus
   static-pose confidence, stability frames, and cooldown. This makes tuning
   possible without editing Python code. The open-palm class remains disabled
   so it can be used during swipes.

9. **Wake-word robustness**  
   Always-on voice retains two-step activation and recognizes common Scribe
   variants such as `orcas`, `orkus`, `orcuss`, `ocus`, and `orcos`.

10. **Explicit confidence outcomes**  
    Existing audit/UI confidence values remain in use, and gesture policy
    rejection now reports the specific gesture threshold that was applied.
    Unrecognized input continues to produce an explicit `no_intent` audit
    entry rather than a success-shaped fallback.

### Latency and scheduling

11. **Pipeline timing**  
    Every pipeline audit entry now includes `timings_ms` for decision, policy,
    execution where applicable, and total processing time.

12. **Preload reporting**  
    Background model/client warmup updates runtime status to `ready` or
    `error`; failures are visible instead of being indistinguishable from a
    successful warmup.

13. **Fast common-command path**  
    With Laya enabled, exact web commands and deterministic rule-based common
    commands run before Laya. Natural-language requests still reach Laya, and
    optional Gemini remains a later fallback.

14. **Non-serializing voice commands**  
    The listener can continue recording while a prior command is executing.
    The bounded queue prevents unlimited memory growth; when full, the runtime
    reports the condition rather than silently dropping the state.

### Hackathon integrations and release UX

15. **ElevenLabs voice output**  
    The dashboard now sends successful action feedback to
    `POST /api/voice/speak`, which uses ElevenLabs TTS when enabled and falls
    back to the browser's speech synthesis when the API key, SDK, or network is
    unavailable. Set `ELEVENLABS_VOICE_ID` to choose a different voice; set
    `ORCUS_TTS=0` to disable server-side TTS.

16. **Gemini fallback hardening**  
    Gemini remains opt-in through `GEMINI_API_KEY`, runs after deterministic
    local routing, and now rejects malformed JSON, unknown actions, non-object
    parameters, invalid confidence values, and oversized transcripts.

17. **Setup and device checks**  
    The dashboard Setup dialog uses `/api/setup` and `/api/devices` to show
    execution mode, integration readiness, camera/microphone availability,
    recorder tools, wake word, and worker health without exposing secrets.

18. **Local-first prize scope**  
    Tiger Data, Backboard, DigitalOcean, Snowflake, Solana, and GoDaddy were
    not added as artificial dependencies. They require credentials,
    provisioning, or a product feature that would expand release risk. The
    current code keeps the local controller functional without any of them;
    Tiger Data remains the best next optional integration for storing the
    emitted timing/health metrics.

19. **Metrics and confirmation safety**  
    `GET /api/metrics` reports in-process sample count, average total pipeline
    latency, and p95 latency. Destructive confirmations expire after
    `confirmation_timeout_seconds` (30 seconds by default), preventing a stale
    pending action from being executed much later.

## Configuration

The relevant defaults are in `config/config.yaml`:

```yaml
gesture_settings:
  camera_index: 0
  static_min_confidence: 0.80
  static_stable_frames: 8
  static_cooldown_seconds: 0.80
  swipe_min_travel: 0.22
  swipe_cooldown_seconds: 0.70

gesture_confidence:
  four_fingers: 0.75
```

For a temporary voice timeout adjustment:

```bash
ORCUS_COMMAND_TIMEOUT=45 orcus
```

## Validation

- Full test suite: **72 passed**
- Python compilation: passed
- JavaScript syntax checks: passed
- `git diff --check`: passed
- Runtime/setup endpoint smoke checks: passed
- Clean dashboard startup smoke check: passed

Hardware-dependent microphone and camera behavior still depends on the active
Linux device, permissions, and `ELEVENLABS_API_KEY`. The runtime now surfaces
those failures through `/api/status` instead of hiding them.

## Future follow-up

The next safe improvements would be a small first-run UI around `/api/setup`,
device enumeration for choosing cameras/microphones, and percentile latency
aggregation from the emitted `timings_ms` records. Those were left out of this
pass to avoid changing the release UI or adding new hardware dependencies.
