"""Subtask 5.4 DoD checks: QR decode integration."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.ml.omr.qr_decode import decode_qr_from_page
from app.services.geometry import qr_box_pixel_rect
from app.services.pdf_gen import load_template, render_version_pdf
from tests.omr_test_utils import make_version_for_render, render_page_rgb, simulate_photo

DPI = 200


@pytest.mark.parametrize("sample_index", range(20))
def test_decodes_correctly_from_20_simulated_photographed_pages(sample_index):
    """Each sample is a different rendered version (distinct qr_id),
    rasterized then run through a simulated-photo pass (blur + lossy JPEG
    recompression, standing in for "rendered-then-photographed") - decoding
    must still recover the exact original qr_id string."""
    quiz_title, version, questions_by_id = make_version_for_render(
        num_questions=5, version_number=sample_index + 1
    )
    pdf_bytes = render_version_pdf(quiz_title, version, questions_by_id)
    template = load_template()

    page_rgb = render_page_rgb(pdf_bytes, dpi=DPI)
    photographed = simulate_photo(page_rgb, blur_ksize=3, jpeg_quality=75)

    decoded = decode_qr_from_page(photographed, template, dpi=DPI)

    assert decoded == version.qr_id


def test_returns_none_for_a_deliberately_occluded_qr_code():
    quiz_title, version, questions_by_id = make_version_for_render(num_questions=5)
    pdf_bytes = render_version_pdf(quiz_title, version, questions_by_id)
    template = load_template()

    page_rgb = render_page_rgb(pdf_bytes, dpi=DPI)
    x0, y0, x1, y1 = qr_box_pixel_rect(template, DPI)
    occluded = page_rgb.copy()
    occluded[y0:y1, x0:x1] = 255  # white out the entire QR box

    result = decode_qr_from_page(occluded, template, dpi=DPI)

    assert result is None


def test_returns_none_rather_than_raising_on_heavy_blur():
    quiz_title, version, questions_by_id = make_version_for_render(num_questions=5)
    pdf_bytes = render_version_pdf(quiz_title, version, questions_by_id)
    template = load_template()

    page_rgb = render_page_rgb(pdf_bytes, dpi=DPI)
    x0, y0, x1, y1 = qr_box_pixel_rect(template, DPI)
    heavily_blurred = page_rgb.copy()
    heavily_blurred[y0:y1, x0:x1] = cv2.GaussianBlur(heavily_blurred[y0:y1, x0:x1], (31, 31), 0)

    result = decode_qr_from_page(heavily_blurred, template, dpi=DPI)

    assert result is None


def test_returns_none_for_an_out_of_bounds_crop():
    template = load_template()
    tiny_image = np.full((10, 10, 3), 255, dtype=np.uint8)

    result = decode_qr_from_page(tiny_image, template, dpi=DPI)

    assert result is None
