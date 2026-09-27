"""Pure swipe detection — no camera, no MediaPipe, just geometry over time.

Ported from the swipe_prototype: the static-pose KNN in the gest-action repo
can't see motion (it normalizes away the wrist position), so swipes are detected
here from the hand's raw position across a short time window. Kept dependency-free
so it unit-tests without hardware.

Feed it (timestamp, x, y) with x, y normalized to [0, 1] frame coordinates.
It returns (gesture_name, confidence) once when a swipe completes, else None.
"""

from __future__ import annotations

from collections import deque

# Tunables (see swipe_prototype.py for the rationale).
WINDOW_SECONDS = 0.5
MIN_TRAVEL = 0.22
MAX_DURATION = 0.6
MAX_CROSS_RATIO = 0.6  # off-axis travel must stay below this * main-axis travel
COOLDOWN_SECONDS = 0.7
HAND_TIMEOUT = 0.5  # tolerate brief detection drops mid-swipe (motion blur)


class SwipeDetector:
    def __init__(
        self,
        *,
        min_travel: float = MIN_TRAVEL,
        cooldown_seconds: float = COOLDOWN_SECONDS,
    ):
        self.buffer: deque[tuple[float, float, float]] = deque()
        self.min_travel = min_travel
        self.cooldown_seconds = cooldown_seconds
        # Negative sentinels so the first swipe isn't swallowed by the cooldown
        # regardless of the clock's base (time.time() vs. a test's t=0).
        self.last_fire = -1e9
        self.last_seen = -1e9

    def reset(self) -> None:
        self.buffer.clear()

    def mark_hand_lost(self, t: float) -> None:
        """Signal that no hand is visible, so stale positions don't fuse into a
        phantom swipe across the gap."""
        self.last_seen = min(self.last_seen, t - HAND_TIMEOUT - 1)

    def update(self, t: float, x: float, y: float) -> tuple[str, float] | None:
        if t - self.last_seen > HAND_TIMEOUT:
            self.reset()
        self.last_seen = t

        self.buffer.append((t, x, y))
        while self.buffer and t - self.buffer[0][0] > WINDOW_SECONDS:
            self.buffer.popleft()

        if t - self.last_fire < self.cooldown_seconds:
            return None
        if len(self.buffer) < 3:
            return None

        t0, x0, y0 = self.buffer[0]
        t1, x1, y1 = self.buffer[-1]
        dx, dy, dt = x1 - x0, y1 - y0, t1 - t0

        if dt <= 0 or dt > MAX_DURATION:
            return None

        # Pick the dominant axis; require enough travel on it and little off-axis.
        if abs(dx) >= abs(dy):
            main, cross = dx, dy
            # Frame is mirrored (selfie view): moving right increases x.
            name = "swipe_right" if dx > 0 else "swipe_left"
        else:
            main, cross = dy, dx
            # y increases downward in frame coords.
            name = "swipe_down" if dy > 0 else "swipe_up"

        if abs(main) < self.min_travel:
            return None
        if abs(cross) > MAX_CROSS_RATIO * abs(main):
            return None  # too diagonal to be a clean directional swipe

        self.last_fire = t
        self.reset()
        return name, _confidence(main, cross, self.min_travel)


def _confidence(main: float, cross: float, min_travel: float = MIN_TRAVEL) -> float:
    """A defensible 0.7-0.99 score: cleaner (straighter, longer) swipes score
    higher. Stays >= 0.7 so a detected swipe clears the policy threshold."""
    straightness = 1.0 - min(1.0, abs(cross) / max(abs(main), 1e-6))
    reach = min(1.0, abs(main) / (2 * min_travel))
    score = 0.7 + 0.29 * (0.5 * straightness + 0.5 * reach)
    return round(min(0.99, score), 2)
