"""Camera-driven gesture input source.

Drives the webcam + MediaPipe Hands, tracks the hand center over time, and
yields normalized GestureEvents when SwipeDetector fires. All OpenCV/MediaPipe
imports are lazy so importing this module (and the test suite) never requires
them; they're only needed when you actually start the camera.

The recognizer stays generic: it emits gesture *names* only. What a swipe means
is decided by config + the decision layer, never here.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from pathlib import Path

from controller.decision.schemas import Event, GestureEvent
from controller.inputs.base import InputSource
from controller.inputs.gesture_detector import SwipeDetector

MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "gesture_knn.pkl"


class GestureInput(InputSource):
    def __init__(
        self,
        camera_index: int = 0,
        show_window: bool = True,
        frame_sink=None,
        static_model: str | Path | None = MODEL_PATH,
    ):
        self.camera_index = camera_index
        self.show_window = show_window
        # Optional callback(frame_bgr) called each frame (with landmarks drawn) —
        # used to stream a live preview without opening the camera twice.
        self.frame_sink = frame_sink
        self.static_model = Path(static_model) if static_model else None
        self._running = False

    def stop(self) -> None:
        self._running = False

    def events(self) -> Iterator[Event]:
        import cv2
        import mediapipe as mp

        static_classifier = None
        if self.static_model and self.static_model.exists():
            from controller.inputs.static_gestures import StaticGestureClassifier

            static_classifier = StaticGestureClassifier(self.static_model)

        mp_hands = mp.solutions.hands
        mp_drawing = mp.solutions.drawing_utils
        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            raise RuntimeError(f"failed to open camera {self.camera_index}")

        hands = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.5,  # lower = steadier tracking, less flicker
            min_tracking_confidence=0.5,
        )
        detector = SwipeDetector()
        self._running = True
        debug = os.environ.get("ORCUS_GESTURE_DEBUG") == "1"
        frames = hands_seen = 0
        try:
            while self._running:
                ok, frame = cap.read()
                if not ok:
                    continue
                frame = cv2.flip(frame, 1)  # mirror for natural interaction
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                results = hands.process(rgb)
                now = time.time()
                frames += 1

                if results.multi_hand_landmarks:
                    hands_seen += 1
                    lm = results.multi_hand_landmarks[0].landmark
                    cx = (lm[0].x + lm[9].x) / 2.0  # wrist + middle-finger MCP
                    cy = (lm[0].y + lm[9].y) / 2.0
                    hit = detector.update(now, cx, cy)
                    if hit is not None:
                        name, confidence = hit
                        yield GestureEvent(name=name, confidence=confidence)
                    if static_classifier is not None:
                        static_hit = static_classifier.update(lm, now)
                        if static_hit is not None:
                            name, confidence = static_hit
                            yield GestureEvent(name=name, confidence=confidence)
                # No else: a single dropped frame must NOT reset the buffer.
                # SwipeDetector.update() already resets when consecutive hand
                # frames are >HAND_TIMEOUT apart (real absence, not flicker).
                elif static_classifier is not None:
                    static_classifier.reset()

                if debug and frames % 30 == 0:
                    print(f"gesture debug: frames={frames} hands_seen={hands_seen}", flush=True)

                if self.frame_sink is not None:
                    if results.multi_hand_landmarks:
                        mp_drawing.draw_landmarks(
                            frame, results.multi_hand_landmarks[0], mp_hands.HAND_CONNECTIONS
                        )
                    self.frame_sink(frame)

                if self.show_window:
                    cv2.imshow("gesture input (q to quit)", frame)
                    if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q")):
                        break
        finally:
            cap.release()
            hands.close()
            if self.show_window:
                cv2.destroyAllWindows()
