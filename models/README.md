# Static gesture model

`gesture_knn.pkl` is the KNN model from the sibling `gest-action` project. It
expects 21 MediaPipe hand landmarks normalized relative to the wrist and scaled
by the furthest landmark (63 float features).

Class labels are mapped in `controller.inputs.static_gestures`:

| Label | Gesture |
|---:|---|
| 0 | zero |
| 1–4 | one to four fingers |
| 6 | fist |
| 7 | thumbs up |
| 8 | thumbs down |

The model's label 5 (`open_palm`) is intentionally ignored so an open hand
remains available for motion-based swipe input.

Install the optional runtime with `uv pip install -e '.[gesture]'`. The model
is gated by confidence and consecutive-frame stability before it emits an
event; swipes continue to use the dependency-free motion detector.
