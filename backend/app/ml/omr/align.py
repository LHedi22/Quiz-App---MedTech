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

# Absolute ceiling on `_best_corner_assignment`'s fit residual (sum of
# squared per-corner errors in canonical destination-pixel space) below
# which a 4-point assignment is trusted at all. Needed once candidate
# search spans multiple scale hypotheses (`_scale_search_hypotheses`): with
# only one fixed scale, `_best_corner_assignment` never had an absolute
# quality gate - it always returned whichever 4-point combo fit best,
# however bad - and got away with it only because a spurious "4th point"
# rarely existed within that one narrow size window. Searching many scales
# makes that bad case reachable (e.g. an occluded/missing real corner
# substituted by some unrelated squarish blob at a size that happens to
# pass a *different* hypothesis's tolerance). Empirically, legitimate fits
# (correct rotation/scale, all 4 real corners present) score well under 1;
# a genuinely wrong substitution scores in the millions - see the
# calibration in PROGRESS.md's scale-invariant-alignment entry. 1000 keeps
# an enormous margin on both sides.
MAX_ACCEPTABLE_RESIDUAL = 1000.0


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


# A live camera photo's effective scale (how large the printed page appears
# in pixels) is arbitrary - unlike a flatbed scan or this test suite's
# digital PDF rasterizations, which are always exactly `dpi`'s scale, a
# phone/webcam photo could show the page occupying anywhere from a small
# fraction to nearly all of the frame, depending only on how far away it was
# held. `align_page` sweeps this range of "as if scanned at this DPI"
# hypotheses when searching for fiducial candidates, rather than assuming
# the upload already matches `dpi` (confirmed live: real captures failed
# with "found 0 fiducial markers" at every resolution/rotation/blur fix
# short of this one - see PROGRESS.md). Log-spaced so adjacent hypotheses'
# +-AREA_TOLERANCE windows on *linear* size fully overlap - the per-step
# ratio (~1.26x) stays under the tolerance window's own ratio (~1.44x, from
# sqrt(1.35)/sqrt(0.65)), so no real fiducial size can fall in a gap between
# two hypotheses that both miss it.
_SCALE_SEARCH_DPI_MIN = 30.0
_SCALE_SEARCH_DPI_MAX = 600.0
_SCALE_SEARCH_STEPS = 14


def _scale_search_hypotheses() -> list[float]:
    log_min, log_max = np.log(_SCALE_SEARCH_DPI_MIN), np.log(_SCALE_SEARCH_DPI_MAX)
    return list(np.exp(np.linspace(log_min, log_max, _SCALE_SEARCH_STEPS)))


def _all_squarish_blob_candidates(gray: np.ndarray) -> list[tuple[float, float, float]]:
    """Locate every blob shaped like a fiducial square anywhere in the
    image, regardless of absolute size - size filtering happens later, per
    scale hypothesis (`_candidates_at_scale`), so the expensive contour
    search itself runs exactly once regardless of how many hypotheses
    `align_page` sweeps. Returns (cx, cy, area) triples.

    `RETR_LIST`, not `RETR_EXTERNAL`: confirmed live from an actual failed
    real-camera scan (a dark-UI-heavy screenshot-viewer background) that
    `RETR_EXTERNAL` (outermost contours only) found 9 total contours and 0
    shape-plausible candidates in the whole frame - almost everything
    merged into a handful of large blobs, hiding every genuinely separate
    smaller shape (fiducials included) as invisible nested structure.
    `RETR_LIST` on the identical image found 1155 contours and 23
    shape-plausible candidates. No committed regression test reproduces
    this exact mechanism (a directly-touching/merged blob, unlike this,
    genuinely can't be un-merged by any retrieval mode - see PROGRESS.md's
    scale-invariant-alignment entry for what was tried and ruled out); this
    is real-world-evidence-backed rather than unit-test-backed, and the
    full existing align.py suite staying green after this change confirms
    it doesn't regress the scenarios that *are* covered.
    """
    _, thresh = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    image_area = gray.shape[0] * gray.shape[1]
    candidates: list[tuple[float, float, float]] = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        # Sanity floor/ceiling only, independent of any scale hypothesis -
        # reject pure noise specks and anything too large to plausibly be a
        # single corner marker (e.g. the whole thresholded page background
        # merged into one contour).
        if area < 25 or area > image_area * 0.05:
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

        candidates.append((cx, cy, area))

    return candidates


def _candidates_at_scale(
    all_candidates: list[tuple[float, float, float]], expected_area_px: float
) -> list[tuple[float, float]]:
    """Narrows the full candidate pool to those matching one scale
    hypothesis's expected fiducial size (+-AREA_TOLERANCE) - keeps the
    per-hypothesis combinatorial search in `_best_corner_assignment` over a
    small, plausible subset rather than every squarish blob in the image."""
    return [
        (cx, cy)
        for cx, cy, area in all_candidates
        if expected_area_px * (1 - AREA_TOLERANCE)
        <= area
        <= expected_area_px * (1 + AREA_TOLERANCE)
    ]


def _normalize_angle_deg(angle_deg: float) -> float:
    a = angle_deg % 360.0
    return a - 360.0 if a > 180.0 else a


def _best_corner_assignment(
    candidates: list[tuple[float, float]], expected: dict[str, tuple[float, float]]
) -> tuple[dict[str, tuple[float, float]], float] | None:
    """Pick 4 of the candidate points and assign each to a named corner by
    finding the assignment whose best-fit similarity transform (rotation +
    uniform scale + translation) onto the expected layout has the least
    residual error. Robust to skew/extra noise candidates, and to the
    candidates being at any uniform scale relative to `expected` - the fit
    itself solves for scale, so this needs no a-priori assumption about how
    large the candidates appear versus the expected (fixed-DPI) layout.

    A rectangle is symmetric under a 180-degree rotation (top_left <->
    bottom_right, top_right <-> bottom_left), so the *correct* correspondence
    and its 180-degree-flipped twin both fit with ~zero residual - picking
    by residual alone is a coin flip between them. A real scan is never
    rotated anywhere near 180 degrees, so among near-tied fits we break the
    tie by preferring the smallest absolute rotation angle.

    Returns `(assignment, residual_error)` - the caller (`align_page`) uses
    the residual to compare fits found under different scale hypotheses and
    keep only the best one, since more than one hypothesis's tolerance
    window can plausibly admit 4 candidates.
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
    chosen_error, _, best_combo = min(
        plausible, key=lambda item: abs(_normalize_angle_deg(item[1]))
    )

    return {name: best_combo[i] for i, name in enumerate(names)}, chosen_error


def align_page(image: np.ndarray, template: dict, dpi: int = 200) -> AlignmentResult:
    """Detect the four corner fiducials in `image` and return a homography-
    corrected copy of it matching the canonical page geometry.

    `dpi` governs only the *output* canonical geometry (the fixed pixel
    space every downstream step - bubble extraction, QR cropping - trusts,
    and what `image` gets warped to). It does NOT assume `image` itself
    already matches that scale: a live camera photo's effective scale is
    arbitrary (the page can occupy any fraction of the frame depending on
    distance), so candidate fiducials are searched for across a swept range
    of scale hypotheses (`_scale_search_hypotheses`), keeping whichever
    hypothesis yields the best-fitting 4-corner assignment.

    Fails gracefully - AlignmentResult(success=False, error=...) - rather
    than raising or silently producing wrong coordinates whenever no scale
    hypothesis yields 4 confidently-located fiducials (e.g. occluded/torn
    corner, or a page that genuinely isn't in frame at all).
    """
    gray = _to_gray(image)
    all_candidates = _all_squarish_blob_candidates(gray)
    expected_px = expected_fiducial_pixels(template, dpi)
    fiducial_size_pt = template["fiducials"]["size_pt"]

    best: tuple[dict[str, tuple[float, float]], float] | None = None
    max_candidates_at_any_scale = 0
    for hypothesis_dpi in _scale_search_hypotheses():
        expected_area_px = (fiducial_size_pt * hypothesis_dpi / 72.0) ** 2
        scale_candidates = _candidates_at_scale(all_candidates, expected_area_px)
        max_candidates_at_any_scale = max(max_candidates_at_any_scale, len(scale_candidates))
        if len(scale_candidates) < 4:
            continue

        fit = _best_corner_assignment(scale_candidates, expected_px)
        if fit is None:
            continue
        assignment, error = fit
        if error <= MAX_ACCEPTABLE_RESIDUAL and (best is None or error < best[1]):
            best = (assignment, error)

    if best is None:
        return AlignmentResult(
            success=False,
            error=f"expected 4 fiducial markers, found {max_candidates_at_any_scale}",
        )

    assignment, _residual = best
    names = list(expected_px.keys())
    src = np.array([assignment[n] for n in names], dtype=np.float32)
    dst = np.array([expected_px[n] for n in names], dtype=np.float32)
    homography = cv2.getPerspectiveTransform(src, dst)

    scale = dpi / 72.0
    page_w_px = int(round(template["page_width_pt"] * scale))
    page_h_px = int(round(template["page_height_pt"] * scale))
    warped = cv2.warpPerspective(image, homography, (page_w_px, page_h_px))

    return AlignmentResult(success=True, warped_image=warped, homography=homography)
