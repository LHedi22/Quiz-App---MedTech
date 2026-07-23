"""Subtask 5.2 DoD checks: bubble region extraction."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from app.ml.omr.align import align_page
from app.ml.omr.extract import extract_bubble_crops
from app.services.geometry import bubble_center_pt, pdf_point_to_pixel
from app.services.pdf_gen import load_template, render_version_pdf
from tests.omr_test_utils import make_version_for_render, render_page_rgb

DPI = 200
OUTPUT_DIR = Path(__file__).parent / "test_output" / "bubble_crops"


def _mark_bubble_filled(
    image: np.ndarray, template: dict, row_index: int, option_index: int, dpi: int
) -> None:
    """Draw a solid black dot directly onto a rendered page raster at a
    bubble's position, simulating a student's pencil-filled answer."""
    x_pt, y_pt = bubble_center_pt(template, row_index, option_index)
    px, py = pdf_point_to_pixel(x_pt, y_pt, template["page_height_pt"], dpi)
    radius_px = int(round(template["bubble_radius_pt"] * dpi / 72.0 * 0.8))
    cv2.circle(image, (int(round(px)), int(round(py))), radius_px, (0, 0, 0), thickness=-1)


def _mean_darkness(crop: np.ndarray) -> float:
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY) if crop.ndim == 3 else crop
    return float(255 - gray.mean())  # higher = darker


def test_crop_count_matches_questions_times_options_for_a_known_page():
    num_questions, num_options = 8, 4
    quiz_title, version, questions_by_id = make_version_for_render(num_questions, num_options)
    pdf_bytes = render_version_pdf(quiz_title, version, questions_by_id)
    template = load_template()

    page_rgb = render_page_rgb(pdf_bytes, dpi=DPI)
    result = align_page(page_rgb, template, dpi=DPI)
    assert result.success

    crops = extract_bubble_crops(result.warped_image, template, num_questions, num_options, dpi=DPI)
    assert len(crops) == num_questions * num_options


@pytest.mark.parametrize(
    "sample_name,num_questions,num_options,filled",
    [
        ("sample_a_8q_4opt", 8, 4, [(0, 1), (3, 3), (7, 0)]),
        ("sample_b_6q_3opt", 6, 3, [(1, 0), (4, 2)]),
        ("sample_c_10q_5opt", 10, 5, [(0, 4), (5, 2), (9, 0)]),
    ],
)
def test_crop_coordinates_are_correct_on_sample_pages(
    sample_name, num_questions, num_options, filled
):
    """Marks specific bubbles as filled on a rendered page, crops every
    bubble, and asserts the darkness signal lands exactly where expected -
    proving crop coordinates are correctly aligned to content, not just
    correctly counted. Crops are also saved to test_output/ for manual
    visual confirmation."""
    quiz_title, version, questions_by_id = make_version_for_render(num_questions, num_options)
    pdf_bytes = render_version_pdf(quiz_title, version, questions_by_id)
    template = load_template()

    page_rgb = render_page_rgb(pdf_bytes, dpi=DPI)
    for row, opt in filled:
        _mark_bubble_filled(page_rgb, template, row, opt, DPI)

    result = align_page(page_rgb, template, dpi=DPI)
    assert result.success

    crops = extract_bubble_crops(result.warped_image, template, num_questions, num_options, dpi=DPI)
    assert len(crops) == num_questions * num_options

    out_dir = OUTPUT_DIR / sample_name
    out_dir.mkdir(parents=True, exist_ok=True)

    filled_set = set(filled)
    darknesses_filled = []
    darknesses_empty = []
    for crop in crops:
        assert crop.image.size > 0, f"empty crop at row={crop.row_index} opt={crop.option_index}"
        darkness = _mean_darkness(crop.image)
        is_filled = (crop.row_index, crop.option_index) in filled_set
        (darknesses_filled if is_filled else darknesses_empty).append(darkness)

        cv2.imwrite(
            str(
                out_dir
                / f"r{crop.row_index}_o{crop.option_index}_{'filled' if is_filled else 'empty'}.png"
            ),
            cv2.cvtColor(crop.image, cv2.COLOR_RGB2BGR),
        )

    # Locked-in assertion (visually spot-checked via the saved PNGs above):
    # every marked bubble's crop is unambiguously darker than every
    # unmarked bubble's crop on the same page.
    assert min(darknesses_filled) > max(
        darknesses_empty
    ), f"marked bubbles not clearly darker: filled={darknesses_filled} empty={darknesses_empty}"
