"""Name-field detection DoD checks.

Text is rendered with cv2.putText (OpenCV's built-in Hershey fonts) rather
than a system TrueType font - guaranteed available on every platform this
runs on (dev machine, CI, Docker), unlike e.g. arial.ttf/DejaVuSans.ttf which
may or may not be installed.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.ml.omr.name_ocr import CONFIDENCE_THRESHOLD, crop_name_field, detect_name
from app.services.pdf_gen import load_template


def _blank_page(template: dict, dpi: int = 200) -> np.ndarray:
    scale = dpi / 72.0
    w = int(round(template["page_width_pt"] * scale))
    h = int(round(template["page_height_pt"] * scale))
    return np.full((h, w, 3), 255, dtype=np.uint8)


def _page_with_name_written(template: dict, text: str, dpi: int = 200) -> np.ndarray:
    """A blank aligned page with `text` drawn, clearly legible, inside the
    name field's crop region."""
    from app.services.geometry import name_field_pixel_rect

    page = _blank_page(template, dpi)
    x0, y0, x1, y1 = name_field_pixel_rect(template, dpi)
    # baseline near the bottom of the crop box, matching where a student
    # would actually write relative to the printed ruled line.
    origin = (x0 + 4, y1 - 6)
    cv2.putText(page, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2, cv2.LINE_AA)
    return page


def _page_with_noise_in_name_field(template: dict, dpi: int = 200) -> np.ndarray:
    from app.services.geometry import name_field_pixel_rect

    rng = np.random.default_rng(20260814)
    page = _blank_page(template, dpi)
    x0, y0, x1, y1 = name_field_pixel_rect(template, dpi)
    page[y0:y1, x0:x1] = rng.integers(0, 256, size=(y1 - y0, x1 - x0, 3), dtype=np.uint8)
    return page


def test_crop_name_field_matches_template_geometry():
    from app.services.geometry import name_field_pixel_rect

    template = load_template()
    page = _blank_page(template)
    expected_x0, expected_y0, expected_x1, expected_y1 = name_field_pixel_rect(template, 200)

    crop = crop_name_field(page, template, dpi=200)
    assert crop.shape[0] == expected_y1 - expected_y0
    assert crop.shape[1] == expected_x1 - expected_x0


def test_detect_name_reads_a_clearly_printed_name():
    template = load_template()
    page = _page_with_name_written(template, "JOHN SMITH")

    result = detect_name(page, template)

    assert "JOHN" in result.text.upper()
    assert "SMITH" in result.text.upper()
    assert result.confidence >= CONFIDENCE_THRESHOLD
    assert result.flagged is False


def test_detect_name_flags_a_blank_field():
    """A blank crop must never be auto-trusted - whether Tesseract reports no
    text at all or hallucinates spurious noise on nothing, flagged=True is
    the invariant that matters here, not the exact text it guessed."""
    template = load_template()
    page = _blank_page(template)

    result = detect_name(page, template)

    assert result.flagged is True
    assert result.confidence < CONFIDENCE_THRESHOLD


def test_detect_name_flags_illegible_noise():
    template = load_template()
    page = _page_with_noise_in_name_field(template)

    result = detect_name(page, template)

    assert result.flagged is True


def test_a_clean_name_is_more_confident_than_illegible_noise():
    """Proves the confidence score actually discriminates legible from
    illegible input, rather than being a constant the gate happens to pass."""
    template = load_template()
    clean = detect_name(_page_with_name_written(template, "JOHN SMITH"), template)
    noisy = detect_name(_page_with_noise_in_name_field(template), template)

    assert clean.confidence > noisy.confidence
    assert noisy.flagged is True
