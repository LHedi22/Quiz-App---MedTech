"""Fiducial-marker based page alignment for scanned OMR sheets.

Every printed page carries five solid black squares - one near each corner
plus a 5th centered on the bottom edge (drawn by
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

# Absolute ceiling on `_best_fiducial_assignment`'s fit residual (sum of
# squared per-marker reprojection errors, in canonical destination-pixel
# space, of a real *homography* fit across all 5 markers) below which an
# assignment is trusted at all. Needed once candidate search spans multiple
# scale hypotheses (`_scale_search_hypotheses`): with only one fixed scale,
# this never had an absolute quality gate - it always returned whichever
# combo fit best, however bad - and got away with it only because a
# spurious extra candidate rarely existed within that one narrow size
# window. Searching many scales makes that bad case reachable (e.g. an
# occluded/missing real corner substituted by some unrelated squarish blob
# at a size that happens to pass a *different* hypothesis's tolerance).
# Empirically, legitimate fits (correct rotation/scale/perspective, all 5
# real markers present) score well under 1; a genuinely wrong substitution
# scores in the thousands or more - see the calibration in PROGRESS.md's
# scale-invariant-alignment and 5th-fiducial entries. 1000 keeps a large
# margin on both sides while still catching wrong substitutions - a real
# homography fit (unlike the similarity-transform fit this replaced) is
# only weakly over-determined by a single redundant point (2 residual
# degrees of freedom against 8 homography parameters), so this threshold
# is deliberately tighter than a full order-of-magnitude margin would
# otherwise suggest; see the occluded-fiducial and keystone regression
# tests in test_align.py, which this value must keep passing.
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

        # A real fiducial is a solid, isolated square with clear background
        # around it - unlike a QR code's own finder/module squares, which
        # are the same shape and (at some scale hypothesis) coincidentally
        # the same apparent size, but packed edge-to-edge against sibling
        # modules with no surrounding white space. Confirmed live: several
        # QR-internal squares slipped past every other check (area, shape,
        # extent, and even `_best_fiducial_assignment`'s convexity/
        # orientation/aspect-ratio checks together) and were accepted as a
        # spurious 5-marker match with near-zero residual (see
        # `test_alignment_fails_gracefully_when_a_fiducial_is_occluded`'s
        # history in PROGRESS.md) - filtering non-isolated candidates out
        # here, at detection time, is more robust than trying to catch every
        # way a QR-derived combination can coincidentally look plausible
        # downstream.
        if not _has_isolated_white_margin(thresh, cx, cy, max(rw, rh)):
            continue

        candidates.append((cx, cy, area))

    return candidates


# Ring width (as a fraction of the candidate's own size) and required
# fraction of that ring that must be background, for a candidate to count as
# an isolated marker - see the isolation check in
# `_all_squarish_blob_candidates`. Calibrated against real measured data: a
# real fiducial's ring reads >=0.95 background regardless of which corner
# (page-edge effects included); a QR-internal module's ring - packed against
# its checkerboard neighbors - reads well under half that even in the most
# favorable observed case (a module adjacent to the QR's own quiet zone).
_ISOLATION_MARGIN_RATIO = 0.5
_ISOLATION_MIN_BACKGROUND_FRACTION = 0.8


def _has_isolated_white_margin(thresh: np.ndarray, cx: float, cy: float, size: float) -> bool:
    """Whether the ring immediately surrounding a candidate square (from its
    own edge out to `_ISOLATION_MARGIN_RATIO` times its size further) is
    mostly background in the thresholded image - `thresh` uses
    `THRESH_BINARY_INV`, so background pixels are 0 and ink is 255."""
    h, w = thresh.shape
    half = size / 2
    outer_half = half * (1 + _ISOLATION_MARGIN_RATIO)
    x0, x1 = int(max(0, cx - outer_half)), int(min(w, cx + outer_half))
    y0, y1 = int(max(0, cy - outer_half)), int(min(h, cy + outer_half))
    if x1 <= x0 or y1 <= y0:
        return False

    region = thresh[y0:y1, x0:x1]
    mask = np.ones(region.shape, dtype=bool)
    ix0, ix1 = int(max(0, cx - half)) - x0, int(min(w, cx + half)) - x0
    iy0, iy1 = int(max(0, cy - half)) - y0, int(min(h, cy + half)) - y0
    mask[max(0, iy0) : max(0, iy1), max(0, ix0) : max(0, ix1)] = False

    ring = region[mask]
    if ring.size == 0:
        return True
    return float(np.mean(ring == 0)) >= _ISOLATION_MIN_BACKGROUND_FRACTION


def _candidates_at_scale(
    all_candidates: list[tuple[float, float, float]], expected_area_px: float
) -> list[tuple[float, float]]:
    """Narrows the full candidate pool to those matching one scale
    hypothesis's expected fiducial size (+-AREA_TOLERANCE) - keeps the
    per-hypothesis combinatorial search in `_best_fiducial_assignment` over a
    small, plausible subset rather than every squarish blob in the image."""
    return [
        (cx, cy)
        for cx, cy, area in all_candidates
        if expected_area_px * (1 - AREA_TOLERANCE)
        <= area
        <= expected_area_px * (1 + AREA_TOLERANCE)
    ]


_CORNER_NAMES = ("top_left", "top_right", "bottom_right", "bottom_left")


def _turn_signs(points: np.ndarray) -> list[float]:
    """Signed cross product of each consecutive pair of edge vectors, walking
    the 4 points in the given cyclic order - positive/negative tells which
    way the path turns at each vertex."""
    signs = []
    n = len(points)
    for i in range(n):
        a, b, c = points[i], points[(i + 1) % n], points[(i + 2) % n]
        cross = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
        signs.append(float(cross))
    return signs


def _is_convex_with_orientation(points: np.ndarray, positive: bool) -> bool:
    """True only if `points`, walked in the given cyclic order, trace a
    convex, non-self-intersecting quadrilateral turning the given direction
    at every vertex.

    Checking only the *aggregate* signed area (its sign alone) isn't enough:
    a self-intersecting ("bowtie") quadrilateral - e.g. swapping just the two
    *adjacent* top_left/top_right candidates while leaving the bottom row and
    aux marker correctly assigned, rather than mirroring the whole rectangle
    - can still land on the same net sign as a proper convex quad, because
    the crossing partially cancels rather than flipping the total (confirmed
    live: exactly this adjacent-pair swap slipped past an aggregate-sign-only
    check with ~zero residual on a real keystone test image - see the
    keystone regression tests in test_align.py). Requiring every one of the
    4 local turns to agree in sign catches both a whole-rectangle mirror
    (every turn flips) and a partial/bowtie swap (turns disagree with each
    other), while still accepting any genuinely convex quadrilateral a real
    photographed page can produce, however rotated or keystoned."""
    signs = _turn_signs(points)
    return all(s > 0 for s in signs) if positive else all(s < 0 for s in signs)


# How far the two candidate "width" sides (top_left-top_right vs
# bottom_left-bottom_right) or the two "height" sides (top_left-bottom_left
# vs top_right-bottom_right) may differ in length, as a ratio, before a
# candidate quadrilateral is rejected as not plausibly a photographed page -
# see `_quad_shape_is_plausible`.
MAX_OPPOSITE_SIDE_RATIO = 4.0
# How far the candidate quadrilateral's own (average width / average height)
# ratio may differ from the true page's, as a ratio-of-ratios, before it's
# rejected - see `_quad_shape_is_plausible`.
MAX_ASPECT_RATIO_DEVIATION = 3.0


def _quad_aspect_ratio(corners_in_cyclic_order: np.ndarray) -> float:
    tl, tr, br, bl = corners_in_cyclic_order
    width = (float(np.hypot(*(tr - tl))) + float(np.hypot(*(br - bl)))) / 2
    height = (float(np.hypot(*(bl - tl))) + float(np.hypot(*(br - tr)))) / 2
    return width / height if height > 0 else float("inf")


def _quad_shape_is_plausible(corners_in_cyclic_order: np.ndarray, ref_aspect: float) -> bool:
    """A homography fit from exactly 4 points is always exact, however
    implausible the 4 points' own shape - so a handful of small, tightly
    clustered noise blobs (confirmed live: candidates from inside a page's
    own QR code, at a scale hypothesis expecting small markers) can still be
    "exactly" homographed onto the widely-separated canonical corners, via
    an extreme/ill-conditioned transform that also happens to place a 5th
    leftover blob near the aux marker's predicted position purely by chance
    - passing both the orientation/convexity check and the aux-residual
    check despite representing no plausible real photograph (see the
    regression test this guards,
    `test_alignment_fails_gracefully_when_a_fiducial_is_occluded`).

    Two independent shape checks, both scale- and rotation-invariant
    (unlike an absolute-size check, which the multi-scale search already
    deliberately avoids relying on - see `_scale_search_hypotheses`):

    1. A real photograph of a rectangular page, however rotated/keystoned,
       keeps its two pairs of opposite sides roughly comparable in length -
       perspective can make the near side of a steeply-angled page
       noticeably longer than the far side, but not by an arbitrary factor.
    2. The candidate's own average-width/average-height ratio must roughly
       match the true page's aspect ratio. Check 1 alone isn't enough: a
       thin, elongated sliver of noise blobs (confirmed live: several QR
       module blobs, tightly clustered) can still have its own two pairs of
       *opposite* sides roughly comparable to each other while being
       nothing like the true page's portrait proportions - a homography
       will happily stretch that sliver into the full page exactly, an
       anisotropic scale far beyond anything a real camera angle produces."""
    if not _quad_shape_is_plausible_sides(corners_in_cyclic_order):
        return False
    cand_aspect = _quad_aspect_ratio(corners_in_cyclic_order)
    if cand_aspect <= 0 or ref_aspect <= 0:
        return False
    deviation = max(cand_aspect / ref_aspect, ref_aspect / cand_aspect)
    return deviation <= MAX_ASPECT_RATIO_DEVIATION


def _quad_shape_is_plausible_sides(corners_in_cyclic_order: np.ndarray) -> bool:
    tl, tr, br, bl = corners_in_cyclic_order
    width_top = float(np.hypot(*(tr - tl)))
    width_bottom = float(np.hypot(*(br - bl)))
    height_left = float(np.hypot(*(bl - tl)))
    height_right = float(np.hypot(*(br - tr)))
    if min(width_top, width_bottom, height_left, height_right) <= 0:
        return False
    return (
        max(width_top, width_bottom) / min(width_top, width_bottom) <= MAX_OPPOSITE_SIDE_RATIO
        and max(height_left, height_right) / min(height_left, height_right)
        <= MAX_OPPOSITE_SIDE_RATIO
    )


def _best_fiducial_assignment(
    candidates: list[tuple[float, float]], expected: dict[str, tuple[float, float]]
) -> tuple[dict[str, tuple[float, float]], float] | None:
    """Pick 4 of the candidate points, assign each to one of the 4 named page
    corners, and fit the *exact* homography those 4 correspondences imply -
    then validate that fit against the remaining candidates using the
    redundant `bottom_offset` marker (or any other names in `expected`
    beyond the 4 corners): whichever leftover candidate that homography
    predicts closest to `bottom_offset`'s expected position becomes this
    assignment's residual. Robust to skew/perspective/extra noise
    candidates, and to the candidates being at any uniform scale relative to
    `expected` - the homography solves for scale/rotation/perspective
    together, so this needs no a-priori assumption about how large the
    candidates appear versus the expected (fixed-DPI) layout.

    Why this two-stage shape (corner-only exact fit + a separate redundant
    check) rather than fitting all 5 points as one combinatorial search: a
    homography computed from exactly 4 point correspondences is always
    *exact* (zero residual) regardless of whether those 4 correspondences
    are actually correct - `cv2.getPerspectiveTransform` has no way to
    disagree with 4 points, so the corner fit alone can never reject a wrong
    assignment. The old similarity-transform fit this replaced tried to get
    a residual signal a different way (rotation + uniform scale +
    translation, 4 DOF) but that model can't represent real keystone/
    perspective distortion at all, so it scored a genuinely keystoned
    photo's *correct* corners with a large, misleading residual -
    indistinguishable from an actually-wrong assignment (see PROGRESS.md's
    Round 4 account: a geometric-plausibility fallback was tried and
    reverted because it couldn't safely tell these apart). Checking the
    corner-fit homography against one independent extra point instead gives
    a real, non-zero residual for a wrong assignment while still fitting a
    genuinely keystoned photo's correct corners with a near-zero one, since
    a homography represents perspective distortion exactly. This also
    removes the previous rotation/reflection relabeling ambiguities (a
    rectangle's 4 corners alone admit several relabelings that all fit a
    4-point transform with ~zero residual: a 180-degree rotation - top_left
    <-> bottom_right, top_right <-> bottom_left - and, since a homography
    can represent a reflection as easily as a rotation, a left-right mirror
    - top_left <-> top_right, bottom_left <-> bottom_right - too) without
    needing the old angle-based tie-break heuristic. This is *why*
    `bottom_offset` is deliberately off-center on both axes rather than
    centered on the bottom edge: a first version of this fix placed the 5th
    marker at the bottom edge's midpoint, which lies exactly on the
    rectangle's left-right mirror axis - a mirrored wrong assignment still
    predicted that marker's position correctly (mirroring a point on the
    mirror axis is a no-op), so it broke the 180-degree ambiguity but not
    the mirror one, and real regression tests (rotated scans - see
    test_align.py) caught mirrored wrong assignments being accepted with
    large real-world coordinate error despite passing the residual gate.
    An off-axis point has no relabeling symmetry left to hide behind: any
    wrong correspondence moves it to a visibly wrong predicted position.

    Searching combinations of 4 (not 5) keeps this the same complexity class
    as the original corner-only search - `itertools.permutations` over 5
    points instead of 4, evaluated with a full homography fit instead of a
    cheap exact 4-point solve, made the per-scale-hypothesis search too slow
    to run in practice (an earlier version of this function tried exactly
    that and made the test suite time out).

    Returns `(assignment, residual_error)` - the caller (`align_page`) uses
    the residual to compare fits found under different scale hypotheses and
    keep only the best one, since more than one hypothesis's tolerance
    window can plausibly admit enough candidates.
    """
    corner_names = [n for n in _CORNER_NAMES if n in expected]
    aux_names = [n for n in expected if n not in corner_names]
    if len(candidates) < len(corner_names) + len(aux_names):
        return None

    corner_ref = np.array([expected[n] for n in corner_names], dtype=np.float32)
    aux_ref = {n: np.array(expected[n], dtype=np.float32) for n in aux_names}
    indices = range(len(candidates))
    # `_CORNER_NAMES` is a cyclic walk around the rectangle (top_left ->
    # top_right -> bottom_right -> bottom_left), so this is a fixed property
    # of the template, not of any particular candidate combo.
    ref_positive = all(s > 0 for s in _turn_signs(corner_ref))
    ref_aspect = _quad_aspect_ratio(corner_ref)

    best: tuple[float, dict[str, tuple[float, float]]] | None = None
    for combo in itertools.permutations(indices, len(corner_names)):
        src = np.array([candidates[i] for i in combo], dtype=np.float32)
        # A homography fit from 4 arbitrary points is exact regardless of
        # whether the correspondence is physically sensible - it can encode
        # a reflection or a self-intersecting ("bowtie") correspondence just
        # as easily as the true rotation/perspective a real photo produces.
        # A camera photographing a flat page in front of it can never
        # produce a mirrored or self-crossing view, so any candidate
        # assignment that isn't a convex quadrilateral with the same
        # winding direction as the true rectangle is physically impossible
        # and rejected outright, before paying for a homography solve at
        # all.
        if not _is_convex_with_orientation(src, ref_positive):
            continue
        if not _quad_shape_is_plausible(src, ref_aspect):
            continue
        matrix = cv2.getPerspectiveTransform(src, corner_ref)

        remaining = [i for i in indices if i not in combo]
        if len(remaining) < len(aux_names):
            continue

        assignment = {name: candidates[combo[i]] for i, name in enumerate(corner_names)}
        total_error = 0.0
        used_remaining: set[int] = set()
        feasible = True
        for aux_name in aux_names:
            best_aux: tuple[float, int] | None = None
            for i in remaining:
                if i in used_remaining:
                    continue
                pred = cv2.perspectiveTransform(
                    np.array([[candidates[i]]], dtype=np.float32), matrix
                )[0][0]
                err = float(np.sum((pred - aux_ref[aux_name]) ** 2))
                if best_aux is None or err < best_aux[0]:
                    best_aux = (err, i)
            if best_aux is None:
                feasible = False
                break
            err, i = best_aux
            used_remaining.add(i)
            total_error += err
            assignment[aux_name] = candidates[i]

        if not feasible:
            continue
        if best is None or total_error < best[0]:
            best = (total_error, assignment)

    if best is None:
        return None
    error, assignment = best
    return assignment, error


def align_page(image: np.ndarray, template: dict, dpi: int = 200) -> AlignmentResult:
    """Detect the 5 fiducial markers in `image` (4 page corners plus the
    redundant `bottom_offset` marker) and return a homography-corrected copy
    of it matching the canonical page geometry.

    `dpi` governs only the *output* canonical geometry (the fixed pixel
    space every downstream step - bubble extraction, QR cropping - trusts,
    and what `image` gets warped to). It does NOT assume `image` itself
    already matches that scale: a live camera photo's effective scale is
    arbitrary (the page can occupy any fraction of the frame depending on
    distance), so candidate fiducials are searched for across a swept range
    of scale hypotheses (`_scale_search_hypotheses`), keeping whichever
    hypothesis yields the best-fitting 5-marker assignment.

    Fails gracefully - AlignmentResult(success=False, error=...) - rather
    than raising or silently producing wrong coordinates whenever no scale
    hypothesis yields 5 confidently-located, geometrically-consistent
    markers (e.g. occluded/torn corner, or a page that genuinely isn't in
    frame at all).
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
        if len(scale_candidates) < len(expected_px):
            continue

        fit = _best_fiducial_assignment(scale_candidates, expected_px)
        if fit is None:
            continue
        assignment, error = fit
        if error <= MAX_ACCEPTABLE_RESIDUAL and (best is None or error < best[1]):
            best = (assignment, error)

    if best is None:
        return AlignmentResult(
            success=False,
            error=(
                f"expected {len(expected_px)} fiducial markers, "
                f"found {max_candidates_at_any_scale}"
            ),
        )

    assignment, _residual = best
    names = list(expected_px.keys())
    src = np.array([assignment[n] for n in names], dtype=np.float32)
    dst = np.array([expected_px[n] for n in names], dtype=np.float32)
    # Least-squares homography across all 5 correspondences (not just an
    # exact 4-point fit) - slightly more accurate than picking any 4 of the
    # 5, and consistent with the fit `_best_fiducial_assignment` scored.
    homography, _mask = cv2.findHomography(src, dst, method=0)

    scale = dpi / 72.0
    page_w_px = int(round(template["page_width_pt"] * scale))
    page_h_px = int(round(template["page_height_pt"] * scale))
    warped = cv2.warpPerspective(image, homography, (page_w_px, page_h_px))

    return AlignmentResult(success=True, warped_image=warped, homography=homography)
