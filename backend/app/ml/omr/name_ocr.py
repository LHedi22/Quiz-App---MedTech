"""Handwritten student-name detection.

Crops the name-field region (see `name_field` in `app/config/pdf_template.json`
and `geometry.name_field_pixel_rect`) out of an already-aligned scanned page
and reads it with Tesseract - a classical OCR engine, not an LLM (CLAUDE.md
Section 2 rule 1 only bans LLM calls; a small trained classifier or, as here,
a deterministic off-the-shelf OCR engine is fine).

Handwriting recognition is inherently far less reliable than reading a filled
bubble, so this module leans on the same confidence-gate pattern as
`app/ml/omr/classify.py` (CLAUDE.md Section 2 rule 5): below
CONFIDENCE_THRESHOLD, or nothing legible at all, the result comes back
flagged and the caller (app/routers/scan.py) must route the submission to
professor review rather than trust the OCR guess. CONFIDENCE_THRESHOLD is a
conservative starting point based on Tesseract's own 0-100 word-confidence
scale, not calibrated against real handwritten scans (no real samples are
available in this dev environment) - like the bubble classifier's threshold
before Phase 9's real-scan calibration, tune this against real scans before
relying on it in production.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
import pytesseract

from app.services.geometry import name_field_pixel_rect

CONFIDENCE_THRESHOLD = 60.0

# Tesseract's word-confidence scale is 0-100; -1 marks a line/block with no
# recognized text at all (not a low-confidence guess), so it's excluded
# rather than averaged in.
_NO_TEXT_CONF = -1

# The name-field crop is small on the printed page (a single handwriting
# line) - Tesseract's accuracy drops sharply below ~20px cap-height, so the
# crop is upscaled before OCR.
_UPSCALE_FACTOR = 3


@dataclass
class NameDetectionResult:
    text: str
    confidence: float  # 0-100, Tesseract's native scale; 0.0 if nothing read
    flagged: bool


def crop_name_field(aligned_image: np.ndarray, template: dict, dpi: int = 200) -> np.ndarray:
    """Crop the handwritten-name region out of an already homography-aligned
    page image, using the same template geometry `align.py`'s output is
    already expressed in."""
    x0, y0, x1, y1 = name_field_pixel_rect(template, dpi)
    img_h, img_w = aligned_image.shape[:2]
    x0, x1 = max(0, x0), min(img_w, x1)
    y0, y1 = max(0, y0), min(img_h, y1)
    return aligned_image[y0:y1, x0:x1]


def _suppress_ruled_line(ink_mask: np.ndarray) -> np.ndarray:
    """Erase the printed ruled line from a binary ink mask (255 = ink, 0 =
    background) without disturbing handwriting strokes.

    Real students write on/touching a ruled line as a matter of course (it's
    what the line is *for*) - the line would otherwise slice straight
    through the bottom of every letter and wreck OCR (verified empirically:
    without this, a clean synthetic "JOHN SMITH" crossing the line came back
    as unreadable garbage). A long, thin horizontal opening kernel isolates
    it: the printed line spans a large fraction of the crop's width in one
    unbroken run, while individual letter strokes - even horizontal ones
    like a "T" crossbar - don't come close to that length.
    """
    width = ink_mask.shape[1]
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(width // 4, 25), 1))
    line_mask = cv2.morphologyEx(ink_mask, cv2.MORPH_OPEN, kernel)
    return cv2.bitwise_and(ink_mask, cv2.bitwise_not(line_mask))


def _preprocess_for_ocr(crop: np.ndarray) -> np.ndarray:
    gray = crop if crop.ndim == 2 else cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    resized = cv2.resize(
        gray, None, fx=_UPSCALE_FACTOR, fy=_UPSCALE_FACTOR, interpolation=cv2.INTER_CUBIC
    )
    # THRESH_BINARY_INV: ink (dark) -> 255, background (light) -> 0, so the
    # morphological line-removal below treats ink as the foreground it opens
    # on. Inverted back to the standard white-background/black-text
    # orientation Tesseract expects afterward.
    _, ink_mask = cv2.threshold(resized, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink_mask = _suppress_ruled_line(ink_mask)
    return cv2.bitwise_not(ink_mask)


def detect_name(aligned_image: np.ndarray, template: dict, dpi: int = 200) -> NameDetectionResult:
    """Crop and OCR the handwritten name field. Always returns a result -
    never raises for illegible/blank input - with `flagged=True` whenever the
    text shouldn't be trusted without professor review."""
    crop = crop_name_field(aligned_image, template, dpi)
    if crop.size == 0:
        return NameDetectionResult(text="", confidence=0.0, flagged=True)

    processed = _preprocess_for_ocr(crop)
    # PSM 7: treat the crop as a single line of text - matches what the
    # name field actually is, and avoids Tesseract trying to segment it into
    # a paragraph/block.
    data = pytesseract.image_to_data(
        processed, output_type=pytesseract.Output.DICT, config="--psm 7"
    )

    words: list[str] = []
    confidences: list[float] = []
    for raw_text, raw_conf in zip(data["text"], data["conf"]):
        text = raw_text.strip()
        conf = float(raw_conf)
        if not text or conf == _NO_TEXT_CONF:
            continue
        words.append(text)
        confidences.append(conf)

    if not words:
        return NameDetectionResult(text="", confidence=0.0, flagged=True)

    full_text = " ".join(words)
    avg_confidence = sum(confidences) / len(confidences)
    flagged = avg_confidence < CONFIDENCE_THRESHOLD
    return NameDetectionResult(text=full_text, confidence=avg_confidence, flagged=flagged)
