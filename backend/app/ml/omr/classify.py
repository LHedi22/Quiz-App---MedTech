"""Bubble fill/empty inference.

Loads the model artifact trained and saved by
`app/ml/bubble_classifier/train.py`. Deliberately does not import that
training module (or scikit-learn's training APIs) - a deployment only needs
this file, `app/ml/bubble_classifier/features.py`, and the saved
`model.joblib` artifact, proving train and inference are properly decoupled.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np

from app.ml.bubble_classifier.features import extract_features

MODEL_PATH = Path(__file__).resolve().parent.parent / "bubble_classifier" / "model.joblib"

# Below this predicted-class probability, don't commit to filled/empty -
# route to "ambiguous" instead. Verified against a dedicated ambiguous-case
# test subset (partial erasure, light marks, mid-range fill, stray marks)
# in backend/tests/test_bubble_classifier.py.
CONFIDENCE_THRESHOLD = 0.85


@lru_cache(maxsize=1)
def _load_model():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"bubble classifier model not found at {MODEL_PATH} - run "
            "`python -m app.ml.bubble_classifier.train` first"
        )
    # joblib.load is pickle-based; safe here because MODEL_PATH is this
    # project's own committed artifact (produced by train.py), never a
    # file supplied by an external/untrusted party.
    return joblib.load(MODEL_PATH)


def classify_bubble(crop: np.ndarray) -> tuple[str, float]:
    """Classify a single cropped bubble region.

    Returns (label, confidence) where label is one of "filled", "empty", or
    "ambiguous" - "ambiguous" whenever the model's confidence in its best
    guess falls below CONFIDENCE_THRESHOLD, regardless of which class it
    leaned toward, so a genuinely uncertain mark is never confidently
    misclassified.
    """
    model = _load_model()
    features = extract_features(crop).reshape(1, -1)
    probabilities = model.predict_proba(features)[0]
    predicted_class = int(np.argmax(probabilities))
    confidence = float(probabilities[predicted_class])

    if confidence < CONFIDENCE_THRESHOLD:
        return "ambiguous", confidence

    return ("filled" if predicted_class == 1 else "empty"), confidence
