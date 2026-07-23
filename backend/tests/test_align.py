"""Subtask 5.1 DoD checks: fiducial-based page alignment."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.ml.omr.align import align_page, expected_fiducial_pixels
from app.services.geometry import bubble_center_pt, pdf_point_to_pixel
from app.services.pdf_gen import load_template, render_version_pdf
from tests.omr_test_utils import (
    forward_point,
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
