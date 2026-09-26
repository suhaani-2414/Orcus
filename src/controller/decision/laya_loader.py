"""Construct a real Laya client (the `laya` package Router).

Router.system_one(state, questions) already matches our LayaClient protocol, so
the Router instance is used directly. Import is lazy and lives here so the rest
of the codebase (and the test suite) never depends on torch/transformers.

The first call downloads a checkpoint (~842MB) and caches it under the HF cache.
"""

from __future__ import annotations

from controller.decision.laya import LayaClient


def load_laya_client(preload: bool = False) -> LayaClient:
    from laya import Router  # type: ignore[attr-defined]  # laya exports Router lazily

    return Router(preload=preload)
