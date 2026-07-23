"""Fiducial-marker based page alignment for scanned OMR sheets.

Every printed page carries four solid black corner squares (drawn by
`app/services/pdf_gen.py::_draw_fiducials`, positioned per the `fiducials`
block of `app/config/pdf_template.json`). This module detects those squares
in a scanned/photographed page image, however rotated or skewed the scan is,
and computes a homography that warps the image back into the same pixel
geometry the template's PDF-point coordinates were designed for. Everything
downstream (bubble-region extraction, QR cropping) then trusts fixed
template coordinates instead of re-deriving geometry per scan.

No LLM or trained model is involved here - purely deterministic OpenCV
contour geometry.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import cv2
import numpy as np

from app.services.geometry import fiducial_centers_pt, pdf_point_to_pixel

CORNER_NAMES = ("top_left", "top_right", "bottom_right", "bottom_left")

# How far a candidate marker's pixel area may deviate from the expected
# fiducial area (at the working DPI) and still be considered. The template's
# fiducial size_pt is deliberately chosen well above a QR finder-pattern's
# outer-square size (the one shape in the rest of the page that could
# otherwise be confused for a fiducial - both are solid black squares), so
# this can stay wide enough to absorb scan-resolution/rotation-interpolation
# variance without admitting a finder pattern.
AREA_TOLERANCE = 0.35
# Extent = contour area / minAreaRect area (its *rotated* bounding rect, so
# this stays ~1.0 for a square regardless of scan rotation - unlike an
# axis-aligned bounding box, whose extent for a rotated square drops toward
# 0.5 at 45 degrees). Circles land near pi/4 ~= 0.785 either way.
MIN_EXTENT = 0.85


@dataclass
class AlignmentResult:
    success: bool
    warped_image: np.ndarray | None = None
    homography: np.ndarray | None = None
    error: str | None = None


def _to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)


def expected_fiducial_pixels(template: dict, dpi: int) -> dict[str, tuple[float, float]]:
    """Where each named corner marker's center *should* land in a
    perfectly-scanned (unrotated) page image at `dpi`."""
    page_h = template["page_height_pt"]
    return {
        name: pdf_point_to_pixel(x, y, page_h, dpi)
        for name, (x, y) in fiducial_centers_pt(template).items()
    }


def _fiducial_candidates(gray: np.ndarray, expected_area_px: float) -> list[tuple[float, float]]:
    """Locate blobs shaped/sized like a fiducial square anywhere in the image."""
    _, thresh = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates: list[tuple[float, float]] = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if not (
            expected_area_px * (1 - AREA_TOLERANCE)
            <= area
            <= expected_area_px * (1 + AREA_TOLERANCE)
        ):
            continue

        perimeter = cv2.arcLength(cnt, True)
        if perimeter == 0:
            continue
        approx = cv2.approxPolyDP(cnt, 0.04 * perimeter, True)
        if len(approx) != 4:
            continue

        # Use the *rotated* min-area rect (not an axis-aligned bounding box)
        # so a marker's aspect/extent read the same regardless of scan
        # rotation - an axis-aligned box's extent for a rotated square drops
        # toward 0.5 at 45 degrees even though the shape is still a square.
        (cx, cy), (rw, rh), _angle = cv2.minAreaRect(cnt)
        if rh == 0 or not (0.7 <= rw / rh <= 1.4):
            continue
        rect_area = rw * rh
        if rect_area == 0 or area / rect_area < MIN_EXTENT:
            continue

        candidates.append((cx, cy))

    return candidates


def _normalize_angle_deg(angle_deg: float) -> float:
    a = angle_deg % 360.0
    return a - 360.0 if a > 180.0 else a


def _best_corner_assignment(
    candidates: list[tuple[float, float]], expected: dict[str, tuple[float, float]]
) -> dict[str, tuple[float, float]] | None:
    """Pick 4 of the candidate points and assign each to a named corner by
    finding the assignment whose best-fit similarity transform (rotation +
    uniform scale + translation) onto the expected layout has the least
    residual error. Robust to skew/extra noise candidates.

    A rectangle is symmetric under a 180-degree rotation (top_left <->
    bottom_right, top_right <-> bottom_left), so the *correct* correspondence
    and its 180-degree-flipped twin both fit with ~zero residual - picking
    by residual alone is a coin flip between them. A real scan is never
    rotated anywhere near 180 degrees, so among near-tied fits we break the
    tie by preferring the smallest absolute rotation angle.
    """
    if len(candidates) < 4:
        return None

    names = list(expected.keys())
    ref_pts = np.array([expected[n] for n in names], dtype=np.float32)

    scored: list[tuple[float, float, tuple]] = []
    for combo in itertools.permutations(candidates, 4):
        src = np.array(combo, dtype=np.float32)
        matrix, _ = cv2.estimateAffinePartial2D(src, ref_pts)
        if matrix is None:
            continue
        transformed = (matrix[:, :2] @ src.T).T + matrix[:, 2]
        error = float(np.sum((transformed - ref_pts) ** 2))
        angle = float(np.degrees(np.arctan2(matrix[1, 0], matrix[0, 0])))
        scored.append((error, angle, combo))

    if not scored:
        return None

    min_error = min(error for error, _, _ in scored)
    error_tolerance = max(min_error * 2, 1.0)
    plausible = [item for item in scored if item[0] <= error_tolerance]
    _, _, best_combo = min(plausible, key=lambda item: abs(_normalize_angle_deg(item[1])))

    return {name: best_combo[i] for i, name in enumerate(names)}


def align_page(image: np.ndarray, template: dict, dpi: int = 200) -> AlignmentResult:
    """Detect the four corner fiducials in `image` and return a homography-
    corrected copy of it matching the canonical page geometry.

    Fails gracefully - AlignmentResult(success=False, error=...) - rather
    than raising or silently producing wrong coordinates whenever fewer than
    4 fiducials can be confidently located (e.g. occluded/torn corner).
    """
    gray = _to_gray(image)
    scale = dpi / 72.0
    expected_area_px = (template["fiducials"]["size_pt"] * scale) ** 2

    candidates = _fiducial_candidates(gray, expected_area_px)
    if len(candidates) < 4:
        return AlignmentResult(
            success=False,
            error=f"expected 4 fiducial markers, found {len(candidates)}",
        )

    expected_px = expected_fiducial_pixels(template, dpi)
    assignment = _best_corner_assignment(candidates, expected_px)
    if assignment is None:
        return AlignmentResult(
            success=False, error="could not match detected markers to page corners"
        )

    names = list(expected_px.keys())
    src = np.array([assignment[n] for n in names], dtype=np.float32)
    dst = np.array([expected_px[n] for n in names], dtype=np.float32)
    homography = cv2.getPerspectiveTransform(src, dst)

    page_w_px = int(round(template["page_width_pt"] * scale))
    page_h_px = int(round(template["page_height_pt"] * scale))
    warped = cv2.warpPerspective(image, homography, (page_w_px, page_h_px))

    return AlignmentResult(success=True, warped_image=warped, homography=homography)
