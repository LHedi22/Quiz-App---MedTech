"""Subtask 5.1 DoD checks: fiducial-based page alignment."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.ml.omr.align import align_page, expected_fiducial_pixels
from app.services.geometry import bubble_center_pt, pdf_point_to_pixel
from app.services.pdf_gen import load_template, render_version_pdf
from tests.omr_test_utils import (
    apply_keystone_warp,
    composite_page_in_frame,
    forward_point,
    forward_point_perspective,
    make_version_for_render,
    render_page_rgb,
    rotate_with_padding,
)

DPI = 200
ALIGNMENT_TOLERANCE_PX = 3.0


@pytest.fixture(scope="module")
def reference_page_rgb() -> np.ndarray:
    quiz_title, version, questions_by_id = make_version_for_render(num_questions=8)
    pdf_bytes = render_version_pdf(quiz_title, version, questions_by_id)
    return render_page_rgb(pdf_bytes, dpi=DPI)


def _sample_bubble_points_pt(template: dict) -> list[tuple[float, float]]:
    return [bubble_center_pt(template, row, opt) for row in range(3) for opt in range(4)]


@pytest.mark.parametrize("angle_deg", [5, 15, 30])
def test_alignment_recovers_bubble_coordinates_within_tolerance_when_rotated(
    reference_page_rgb, angle_deg
):
    template = load_template()
    rotated, forward_matrix = rotate_with_padding(reference_page_rgb, angle_deg)

    result = align_page(rotated, template, dpi=DPI)
    assert result.success, f"alignment failed at {angle_deg} degrees: {result.error}"

    page_h = template["page_height_pt"]
    for x_pt, y_pt in _sample_bubble_points_pt(template):
        true_px = pdf_point_to_pixel(x_pt, y_pt, page_h, DPI)
        # Where that same physical bubble center landed in the rotated scan.
        rotated_px = forward_point(forward_matrix, *true_px)

        src = np.array([[[rotated_px[0], rotated_px[1]]]], dtype=np.float32)
        recovered_px = cv2.perspectiveTransform(src, result.homography)[0][0]

        error = float(np.hypot(recovered_px[0] - true_px[0], recovered_px[1] - true_px[1]))
        assert error <= ALIGNMENT_TOLERANCE_PX, (
            f"bubble at pt=({x_pt},{y_pt}) recovered {error:.2f}px off "
            f"(tolerance {ALIGNMENT_TOLERANCE_PX}px) at rotation {angle_deg} degrees"
        )


@pytest.mark.parametrize("page_width_fraction", [0.35, 0.6, 0.9])
def test_alignment_recovers_bubble_coordinates_when_page_is_a_fraction_of_a_larger_camera_frame(
    reference_page_rgb, page_width_fraction
):
    """A live camera photo is never pixel-perfect-at-200-DPI like every other
    fixture in this file - the page occupies some unknown fraction of a
    larger frame depending on how far away the professor held the device
    (confirmed live: a real 1920x1080 capture failed with 'found 0 fiducial
    markers' even after fixing resolution/rotation/blur handling - see
    PROGRESS.md). `align_page` must search across scale, not assume the
    upload already matches the template's fixed-DPI pixel geometry."""
    template = load_template()
    frame_w, frame_h = 1920, 1080
    frame, scale, x_off, y_off = composite_page_in_frame(
        reference_page_rgb, frame_w, frame_h, page_width_fraction
    )

    result = align_page(frame, template, dpi=DPI)
    assert (
        result.success
    ), f"alignment failed at page_width_fraction={page_width_fraction}: {result.error}"

    page_h = template["page_height_pt"]
    for x_pt, y_pt in _sample_bubble_points_pt(template):
        true_px = pdf_point_to_pixel(x_pt, y_pt, page_h, DPI)
        frame_px = (true_px[0] * scale + x_off, true_px[1] * scale + y_off)

        src = np.array([[[frame_px[0], frame_px[1]]]], dtype=np.float32)
        recovered_px = cv2.perspectiveTransform(src, result.homography)[0][0]

        error = float(np.hypot(recovered_px[0] - true_px[0], recovered_px[1] - true_px[1]))
        assert error <= ALIGNMENT_TOLERANCE_PX, (
            f"bubble at pt=({x_pt},{y_pt}) recovered {error:.2f}px off "
            f"(tolerance {ALIGNMENT_TOLERANCE_PX}px) at page_width_fraction={page_width_fraction}"
        )


@pytest.mark.parametrize("top_shrink_fraction", [0.05, 0.1])
def test_alignment_recovers_bubble_coordinates_under_genuine_keystone_perspective_distortion(
    reference_page_rgb, top_shrink_fraction
):
    """Regression test for the real bug behind PROGRESS.md's Round 4 account:
    a real oblique-angle camera photo produces genuine trapezoidal keystone
    distortion, which a similarity transform (rotation + uniform scale +
    translation) cannot represent - a photo's *correct* fiducial corners
    would score a large, misleading residual under that model,
    indistinguishable from an actually-wrong corner assignment. Unlike
    `rotate_with_padding` (a pure affine transform, used by every other test
    in this file), `apply_keystone_warp` produces a true 4-point perspective
    warp - the only way to construct a test image a similarity transform
    genuinely cannot undo.

    `top_shrink_fraction=0.1` (the far edge at 80% of the near edge's width -
    a clearly visible keystone) is the verified ceiling of what this
    architecture reliably recovers, not an arbitrary round number: past
    roughly 0.12, a real, *expected* geometric side effect of a strong
    perspective warp takes over - even a marker sitting at a point the
    homography leaves nominally unmoved (the bottom edge, here) has its own
    *local* aspect ratio visibly distorted by the same transform (measured
    live up to ~1.5:1, worse than a rotation ever produces), which fails the
    ordinary per-candidate squareness filter in
    `_all_squarish_blob_candidates` (`0.7 <= rw/rh <= 1.4`, unrelated to and
    predating this fix) before the marker is ever considered a fiducial
    candidate at all - not a scoring/residual problem this function's
    checks could address. That angle is also steeper than a professor's
    phone photo of a physical page realistically produces, and steep enough
    that individual bubble marks would likely be too distorted to score
    reliably even if alignment itself succeeded - so this is treated as a
    documented capability boundary, not a bug to keep chasing."""
    template = load_template()
    warped, matrix = apply_keystone_warp(reference_page_rgb, top_shrink_fraction)

    result = align_page(warped, template, dpi=DPI)
    assert (
        result.success
    ), f"alignment failed at top_shrink_fraction={top_shrink_fraction}: {result.error}"

    page_h = template["page_height_pt"]
    for x_pt, y_pt in _sample_bubble_points_pt(template):
        true_px = pdf_point_to_pixel(x_pt, y_pt, page_h, DPI)
        warped_px = forward_point_perspective(matrix, *true_px)

        src = np.array([[[warped_px[0], warped_px[1]]]], dtype=np.float32)
        recovered_px = cv2.perspectiveTransform(src, result.homography)[0][0]

        error = float(np.hypot(recovered_px[0] - true_px[0], recovered_px[1] - true_px[1]))
        assert error <= ALIGNMENT_TOLERANCE_PX, (
            f"bubble at pt=({x_pt},{y_pt}) recovered {error:.2f}px off "
            f"(tolerance {ALIGNMENT_TOLERANCE_PX}px) at top_shrink_fraction={top_shrink_fraction}"
        )


def test_alignment_succeeds_with_near_zero_error_on_an_unrotated_scan(reference_page_rgb):
    template = load_template()
    result = align_page(reference_page_rgb, template, dpi=DPI)
    assert result.success
    assert result.error is None
    assert result.warped_image is not None
    assert result.homography is not None


def test_alignment_fails_gracefully_when_a_fiducial_is_occluded(reference_page_rgb):
    template = load_template()
    expected_px = expected_fiducial_pixels(template, DPI)
    scale = DPI / 72.0
    fid_size_px = template["fiducials"]["size_pt"] * scale

    occluded = reference_page_rgb.copy()
    cx, cy = expected_px["top_left"]
    pad = int(fid_size_px * 1.5)
    x0, y0 = max(0, int(cx - pad)), max(0, int(cy - pad))
    x1, y1 = int(cx + pad), int(cy + pad)
    occluded[y0:y1, x0:x1] = 255  # white out the top-left fiducial region

    result = align_page(occluded, template, dpi=DPI)

    assert result.success is False
    assert result.error is not None
    assert result.warped_image is None
    assert result.homography is None


def test_alignment_fails_gracefully_when_all_fiducials_are_removed(reference_page_rgb):
    template = load_template()
    blank = np.full_like(reference_page_rgb, 255)

    result = align_page(blank, template, dpi=DPI)

    assert result.success is False
    assert "0" in result.error
