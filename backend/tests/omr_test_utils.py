"""Shared synthetic scan-image helpers for Phase 5 OMR tests.

Builds a version PDF via the real Phase 4 renderer, rasterizes it with
PyMuPDF, and can rotate/blur/recompress the raster to simulate a skewed scan
or a photographed (not scanned) page - all without any external test-fixture
image files, so the whole OMR test suite is reproducible from code alone.
"""

from __future__ import annotations

import io
import uuid

import cv2
import fitz
import numpy as np
from PIL import Image

from app.models.version import QuestionForRender, VersionForRender


def make_version_for_render(
    num_questions: int, num_options: int = 4, version_number: int = 1
) -> tuple[str, VersionForRender, dict]:
    questions = []
    option_order = {}
    question_order = []
    for i in range(num_questions):
        qid = uuid.uuid4()
        question_order.append(qid)
        options = [f"Option {j} for Q{i + 1}" for j in range(num_options)]
        questions.append(
            QuestionForRender(id=qid, text=f"Question {i + 1} text goes here?", options=options)
        )
        option_order[str(qid)] = list(range(num_options))

    questions_by_id = {q.id: q for q in questions}
    version = VersionForRender(
        id=uuid.uuid4(),
        quiz_id=uuid.uuid4(),
        version_number=version_number,
        qr_id=str(uuid.uuid4()),
        question_order=question_order,
        option_order=option_order,
    )
    return "Sample Quiz", version, questions_by_id


def render_page_rgb(pdf_bytes: bytes, page_index: int = 0, dpi: int = 200) -> np.ndarray:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc[page_index]
    pix = page.get_pixmap(dpi=dpi)
    image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    return np.array(image)


def write_name_on_page(image: np.ndarray, template: dict, text: str, dpi: int = 200) -> None:
    """Draws `text` into the name field's crop region in place, simulating a
    student having handwritten their name just *above* the printed ruled
    line (not on top of it - a baseline anchored to the crop's bottom edge
    would sit right on the rendered line and get sliced through it, unlike
    real handwriting which sits above the line it's ruled against).
    cv2.putText (a built-in Hershey font) rather than a system TrueType font,
    so this works identically on every platform this test suite runs on."""
    from app.services.geometry import name_field_pixel_rect, pdf_point_to_pixel

    x0, y0, _x1, _y1 = name_field_pixel_rect(template, dpi)
    field = template["name_field"]
    _, line_py = pdf_point_to_pixel(
        field["line_x0_pt"], field["line_y_pt"], template["page_height_pt"], dpi
    )
    origin = (x0 + 4, int(round(line_py)) - 4)
    cv2.putText(image, text, origin, cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2, cv2.LINE_AA)


def rotate_with_padding(image: np.ndarray, angle_deg: float) -> tuple[np.ndarray, np.ndarray]:
    """Rotate `image` by `angle_deg` about its center, expanding the canvas
    (white-filled) so nothing is cropped. Returns the rotated image and the
    2x3 forward affine matrix used, so callers can map a known reference
    point into the rotated image's coordinate space."""
    h, w = image.shape[:2]
    center = (w / 2, h / 2)
    matrix = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])
    new_w = int(h * sin + w * cos)
    new_h = int(h * cos + w * sin)
    matrix[0, 2] += (new_w / 2) - center[0]
    matrix[1, 2] += (new_h / 2) - center[1]
    rotated = cv2.warpAffine(image, matrix, (new_w, new_h), borderValue=(255, 255, 255))
    return rotated, matrix


def forward_point(matrix: np.ndarray, x: float, y: float) -> tuple[float, float]:
    vec = np.array([x, y, 1.0])
    out = matrix @ vec
    return float(out[0]), float(out[1])


def simulate_photo(image: np.ndarray, blur_ksize: int = 3, jpeg_quality: int = 70) -> np.ndarray:
    """Roughly approximate a phone-photo (vs. a clean digital render): a
    little blur plus lossy JPEG recompression."""
    blurred = cv2.GaussianBlur(image, (blur_ksize, blur_ksize), 0)
    ok, encoded = cv2.imencode(".jpg", blurred, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
    if not ok:
        return blurred
    return cv2.imdecode(encoded, cv2.IMREAD_COLOR)
