"""Synthetic bubble-crop generator used as the bubble classifier's training
data (see app/ml/README.md for why: no real scanned exam data exists yet).

Renders a printed bubble outline plus a programmatically-controlled ink fill
(varying fill percentage, Gaussian noise, small random rotation), and can
also produce deliberately ambiguous cases - partial erasure, a faint/light
mark, or a stray mark near an otherwise-empty bubble - used to verify that
the classifier routes uncertain input to low confidence instead of guessing.
"""

from __future__ import annotations

import cv2
import numpy as np

BASE_SIZE = 64
BUBBLE_RADIUS = 20
OUTLINE_GRAY = 60
FILL_GRAY = 20


def generate_bubble_crop(
    rng: np.random.Generator,
    fill_fraction: float,
    *,
    noise_std: float = 8.0,
    stray_mark: bool = False,
    partial_erasure: bool = False,
    faint: bool = False,
) -> np.ndarray:
    """A single synthetic grayscale bubble crop. `fill_fraction` in [0, 1]
    controls how much of the bubble's area is inked (area-proportional, not
    radius-proportional, to mimic how a real partial fill looks)."""
    img = np.full((BASE_SIZE, BASE_SIZE), 255, dtype=np.uint8)
    center = (BASE_SIZE // 2, BASE_SIZE // 2)
    cv2.circle(img, center, BUBBLE_RADIUS, color=OUTLINE_GRAY, thickness=2)

    if fill_fraction > 0:
        fill_radius = max(1, int(BUBBLE_RADIUS * np.sqrt(fill_fraction)))
        cv2.circle(img, center, fill_radius, color=FILL_GRAY, thickness=-1)

        if partial_erasure:
            erase_center = (
                center[0] + int(rng.integers(-fill_radius // 2, fill_radius // 2 + 1)),
                center[1] + int(rng.integers(-fill_radius // 2, fill_radius // 2 + 1)),
            )
            # Large enough to knock the remaining ink down to genuinely
            # ambiguous territory (~50% ish of the bubble), not just a
            # cosmetic nick that still reads as clearly filled.
            erase_radius = int(BUBBLE_RADIUS * 0.6)
            cv2.circle(img, erase_center, erase_radius, color=255, thickness=-1)

    if stray_mark:
        offset = rng.integers(BUBBLE_RADIUS + 1, BUBBLE_RADIUS + 5)
        angle = rng.uniform(0, 2 * np.pi)
        sx = int(center[0] + offset * np.cos(angle))
        sy = int(center[1] + offset * np.sin(angle))
        sx = int(np.clip(sx, 2, BASE_SIZE - 3))
        sy = int(np.clip(sy, 2, BASE_SIZE - 3))
        cv2.circle(img, (sx, sy), int(rng.integers(2, 4)), color=40, thickness=-1)

    if faint:
        # Attenuation calibrated (see PROGRESS.md 5.3) so a light/faded pencil
        # mark's darkness lands near the empty/filled midpoint - genuinely
        # ambiguous, not just a duller version of an obviously-filled bubble.
        attenuation = float(rng.uniform(0.45, 0.6))
        img = np.clip(
            img.astype(np.float64) * attenuation + 255 * (1 - attenuation), 0, 255
        ).astype(np.uint8)

    if noise_std > 0:
        noise = rng.normal(0, noise_std, img.shape)
        img = np.clip(img.astype(np.float64) + noise, 0, 255).astype(np.uint8)

    rotation_matrix = cv2.getRotationMatrix2D(center, float(rng.uniform(-10, 10)), 1.0)
    img = cv2.warpAffine(img, rotation_matrix, (BASE_SIZE, BASE_SIZE), borderValue=255)

    return img


def generate_labeled_dataset(
    rng: np.random.Generator, n_per_class: int = 400
) -> tuple[list[np.ndarray], list[int]]:
    """Unambiguous filled (1) vs. empty (0) examples - the held-out accuracy
    DoD is measured against this set. Fill/empty fractions are kept clearly
    separated (>=85% or <=8%) since mid-range fill belongs to the ambiguous
    set, not the accuracy benchmark."""
    crops: list[np.ndarray] = []
    labels: list[int] = []

    for _ in range(n_per_class):
        crop = generate_bubble_crop(
            rng, fill_fraction=float(rng.uniform(0.85, 1.0)), stray_mark=bool(rng.random() < 0.1)
        )
        crops.append(crop)
        labels.append(1)

    for _ in range(n_per_class):
        crop = generate_bubble_crop(
            rng, fill_fraction=float(rng.uniform(0.0, 0.08)), stray_mark=bool(rng.random() < 0.1)
        )
        crops.append(crop)
        labels.append(0)

    return crops, labels


def generate_ambiguous_dataset(
    rng: np.random.Generator, n: int = 200
) -> tuple[list[np.ndarray], list[str]]:
    """Deliberately hard cases: partial erasure, a light/faint mark, a
    mid-range fill, or a stray mark near an empty bubble. None of these
    should be confidently classified either way."""
    crops: list[np.ndarray] = []
    kinds: list[str] = []
    kind_choices = ("mid_fill", "partial_erasure", "light_mark", "stray_only")

    for _ in range(n):
        kind = str(rng.choice(kind_choices))
        if kind == "mid_fill":
            crop = generate_bubble_crop(rng, fill_fraction=float(rng.uniform(0.35, 0.65)))
        elif kind == "partial_erasure":
            crop = generate_bubble_crop(
                rng, fill_fraction=float(rng.uniform(0.75, 0.95)), partial_erasure=True
            )
        elif kind == "light_mark":
            crop = generate_bubble_crop(
                rng, fill_fraction=float(rng.uniform(0.85, 1.0)), faint=True
            )
        else:  # stray_only
            crop = generate_bubble_crop(rng, fill_fraction=0.0, stray_mark=True)

        crops.append(crop)
        kinds.append(kind)

    return crops, kinds
