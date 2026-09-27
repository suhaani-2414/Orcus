"""Static hand-pose classification backed by the gest-action KNN model.

The model consumes the same 21 MediaPipe landmarks as the gesture input:
translation- and scale-normalized x/y/z coordinates (63 floats). The sklearn
and pickle imports stay lazy so users who only want voice or swipe input do not
need the optional gesture-model dependencies.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

import numpy as np

from controller.inputs.gesture_labels import MODEL_LABELS


def landmarks_to_vector(landmarks: Any) -> np.ndarray:
    """Convert MediaPipe hand landmarks to the gest-action feature vector."""
    points = np.asarray([(lm.x, lm.y, lm.z) for lm in landmarks], dtype=np.float32)
    if points.shape != (21, 3):
        raise ValueError(f"expected 21 hand landmarks, got {points.shape}")
    points -= points[0]
    scale = float(np.linalg.norm(points, axis=1).max())
    if scale <= 1e-6:
        raise ValueError("hand landmarks have zero size")
    return (points / scale).flatten()


class StaticGestureClassifier:
    """Load the optional KNN model and emit stable pose predictions."""

    def __init__(
        self,
        model_path: str | Path,
        *,
        min_confidence: float = 0.8,
        stable_frames: int = 8,
        cooldown_seconds: float = 0.8,
    ):
        import pickle

        with Path(model_path).open("rb") as model_file:
            self.model = pickle.load(model_file)
        if getattr(self.model, "n_features_in_", 63) != 63:
            raise ValueError("static gesture model must accept 63 features")
        self.min_confidence = min_confidence
        self.history: deque[str] = deque(maxlen=stable_frames)
        self.cooldown_seconds = cooldown_seconds
        self.last_fire = -float("inf")
        self.armed = True

    def update(self, landmarks: Any, timestamp: float) -> tuple[str, float] | None:
        vector = landmarks_to_vector(landmarks)
        probabilities = self.model.predict_proba([vector])[0]
        index = int(np.argmax(probabilities))
        confidence = float(probabilities[index])
        name = MODEL_LABELS.get(int(self.model.classes_[index]))
        if name is None or confidence < self.min_confidence:
            self.history.clear()
            self.armed = True
            return None

        self.history.append(name)
        stable = len(self.history) == self.history.maxlen and len(set(self.history)) == 1
        if not stable:
            return None
        if not self.armed or timestamp - self.last_fire < self.cooldown_seconds:
            return None

        self.last_fire = timestamp
        self.armed = False
        return name, round(confidence, 2)

    def reset(self) -> None:
        self.history.clear()
        self.armed = True
