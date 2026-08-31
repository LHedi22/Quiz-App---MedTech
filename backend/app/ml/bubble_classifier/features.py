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


# Floor on the estimated background level before normalizing against it -
# guards a degenerate crop (e.g. a corner that genuinely contains dark
# content) from being amplified toward implausible values; real observed
# backgrounds (including the darkest real-photo case measured) never come
# close to this floor.
MIN_BACKGROUND_LEVEL = 100.0


def _background_level(gray: np.ndarray) -> float:
    """Median pixel value in the crop's four corners - the one region
    `extract_bubble_crops`'s padding guarantees is background, never the
    printed bubble stroke or a real fill (see CROP_PADDING_PT). Median, not
    mean, so a handful of noisy/stray pixels in the sample don't skew the
    estimate."""
    h, w = gray.shape
    corner = max(1, int(round(min(h, w) * 0.15)))
    samples = np.concatenate(
        [
            gray[:corner, :corner].ravel(),
            gray[:corner, -corner:].ravel(),
            gray[-corner:, :corner].ravel(),
            gray[-corner:, -corner:].ravel(),
        ]
    )
    return float(np.median(samples))


def extract_features(crop: np.ndarray) -> np.ndarray:
    """Return a fixed-length feature vector describing how dark/filled a
    single bubble crop is, and whether that darkness is concentrated in the
    bubble's center (a real fill) vs. its outer ring (a stray mark grazing
    the crop's edge, or just the printed outline).

    Normalizes each crop's own corner-estimated background level to a fixed
    reference before computing darkness - confirmed live (2026-08-31 real-
    submission debugging) that a real photographed page can carry a genuine
    ambient-lighting gradient across its own physical area (measured: pure
    background pixel value dropping from ~225 near the top of a real page
    to ~202 near the bottom, unrelated to alignment or fill content), which
    otherwise reads as partial fill evidence to every one of this module's
    darkness-based features and pushes genuinely-empty bubbles toward
    "ambiguous". Training the classifier to be robust to that range instead
    (via synthetic brightness augmentation) was tried first and reverted -
    it also eroded sensitivity to genuinely faint/attenuated real marks,
    since both phenomena manifest as reduced absolute darkness in the same
    features. Normalizing here instead decouples the two: a genuinely-empty
    bubble's *local* background is corrected back to the same reference a
    clean digital render would show, while a genuinely-faint mark's
    attenuation - a contrast reduction *relative to its own already-
    normalized local background*, not an absolute-darkness effect - is
    untouched. See real_camera_scan_alignment_gap memory's 2026-08-31
    update for the full evidence trail, including both reverted attempts."""
    gray = _to_gray(crop)
    if gray.shape[:2] != (CANONICAL_SIZE, CANONICAL_SIZE):
        gray = cv2.resize(gray, (CANONICAL_SIZE, CANONICAL_SIZE), interpolation=cv2.INTER_AREA)

    background = max(_background_level(gray), MIN_BACKGROUND_LEVEL)
    normalized = np.clip(gray.astype(np.float64) * (255.0 / background), 0, 255)

    darkness = 1.0 - (normalized / 255.0)  # 0 = white, 1 = black

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
