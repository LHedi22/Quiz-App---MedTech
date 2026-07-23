"""Pixel-darkness feature engineering for the bubble-fill classifier.

Shared, byte-for-byte, by both the training pipeline
(app/ml/bubble_classifier/train.py) and inference (app/ml/omr/classify.py) -
the two must never compute features differently. Deliberately dependency-
light (numpy/opencv only, no sklearn) since inference should not need to
import anything training-only.

Crops are resized to a fixed canonical size first, so the feature vector
doesn't depend on the working DPI or the crop-padding constant used by
app/ml/omr/extract.py.
"""

from __future__ import annotations

import cv2
import numpy as np

CANONICAL_SIZE = 32
FEATURE_NAMES = ("mean_darkness", "std_darkness", "dark_fraction", "inner_mean", "ring_mean")


def _to_gray(crop: np.ndarray) -> np.ndarray:
    if crop.ndim == 2:
        return crop
    return cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)


def extract_features(crop: np.ndarray) -> np.ndarray:
    """Return a fixed-length feature vector describing how dark/filled a
    single bubble crop is, and whether that darkness is concentrated in the
    bubble's center (a real fill) vs. its outer ring (a stray mark grazing
    the crop's edge, or just the printed outline)."""
    gray = _to_gray(crop)
    if gray.shape[:2] != (CANONICAL_SIZE, CANONICAL_SIZE):
        gray = cv2.resize(gray, (CANONICAL_SIZE, CANONICAL_SIZE), interpolation=cv2.INTER_AREA)

    darkness = 1.0 - (gray.astype(np.float64) / 255.0)  # 0 = white, 1 = black

    h, w = darkness.shape
    cy, cx = h / 2.0, w / 2.0
    yy, xx = np.mgrid[0:h, 0:w]
    dist = np.hypot(yy - cy, xx - cx)
    max_radius = min(h, w) / 2.0

    inner_mask = dist <= max_radius * 0.6
    ring_mask = (dist > max_radius * 0.6) & (dist <= max_radius * 0.95)

    mean_darkness = float(darkness.mean())
    std_darkness = float(darkness.std())
    dark_fraction = float((darkness > 0.5).mean())
    inner_mean = float(darkness[inner_mask].mean()) if inner_mask.any() else 0.0
    ring_mean = float(darkness[ring_mask].mean()) if ring_mask.any() else 0.0

    return np.array([mean_darkness, std_darkness, dark_fraction, inner_mean, ring_mean])
