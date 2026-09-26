"""Construct a real Laya client.

Prefers a locally fine-tuned checkpoint at training/laya-finetuned/ if present
(loaded via RLAgent, which takes a local path); otherwise falls back to the base
model via the package Router. Both expose system_one, matching LayaClient.

Imports are lazy and live here so the rest of the codebase (and the test suite)
never depends on torch/transformers. The base model's first use downloads a
checkpoint (~842MB) into the HF cache.
"""

from __future__ import annotations

from pathlib import Path

from controller.decision.laya import LayaClient

# training/laya-finetuned/ relative to the repo root (…/src/controller/decision/).
FINETUNED_DIR = Path(__file__).resolve().parents[3] / "training" / "laya-finetuned"


def load_laya_client(preload: bool = False, device: str | None = None) -> LayaClient:
    if (FINETUNED_DIR / "model.safetensors").exists():
        from laya import RLAgent  # type: ignore[attr-defined]

        return RLAgent(str(FINETUNED_DIR), device=device)

    from laya import Router  # type: ignore[attr-defined]  # laya exports Router lazily

    return Router(preload=preload)
