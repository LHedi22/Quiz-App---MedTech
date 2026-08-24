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


def composite_page_in_frame(
    page_rgb: np.ndarray,
    frame_width: int,
    frame_height: int,
    page_width_fraction: float,
    background_value: int = 235,
) -> tuple[np.ndarray, float, float, float]:
    """Places `page_rgb`, scaled down, onto a larger synthetic 'camera frame'
    canvas with background margin on all sides - simulating a real camera
    photo, where the page occupies some unknown fraction of the frame
    depending on how far away it was held, unlike every other fixture in
    this test suite, which renders the page at exactly the fixed 200 DPI
    `align_page` assumes fills the whole image. `page_width_fraction`
    controls how much of the frame's width the scaled page occupies (page
    height follows from its own aspect ratio, so the page may not touch the
    frame's top/bottom edges either).

    Returns `(frame, scale, x_offset, y_offset)`: `scale` is the uniform
    factor from `page_rgb` pixel coordinates to `frame` pixel coordinates,
    and `x_offset`/`y_offset` the page's top-left placement in the frame -
    together, a caller can map any known point in `page_rgb` into `frame`
    the same way `rotate_with_padding`'s `forward_point` does for rotation,
    to verify a recovered homography without any ambiguity about placement.
    """
    page_h, page_w = page_rgb.shape[:2]
    scale = (frame_width * page_width_fraction) / page_w
    scaled_w = max(1, int(round(page_w * scale)))
    scaled_h = max(1, int(round(page_h * scale)))
    if scaled_h > frame_height:
        scale *= frame_height / scaled_h
        scaled_w = max(1, int(round(page_w * scale)))
        scaled_h = max(1, int(round(page_h * scale)))

    scaled_page = cv2.resize(page_rgb, (scaled_w, scaled_h), interpolation=cv2.INTER_AREA)
    frame = np.full((frame_height, frame_width, 3), background_value, dtype=np.uint8)
    x_offset = (frame_width - scaled_w) // 2
    y_offset = (frame_height - scaled_h) // 2
    frame[y_offset : y_offset + scaled_h, x_offset : x_offset + scaled_w] = scaled_page
    return frame, scale, float(x_offset), float(y_offset)


def simulate_photo(image: np.ndarray, blur_ksize: int = 3, jpeg_quality: int = 70) -> np.ndarray:
    """Roughly approximate a phone-photo (vs. a clean digital render): a
    little blur plus lossy JPEG recompression."""
    blurred = cv2.GaussianBlur(image, (blur_ksize, blur_ksize), 0)
    ok, encoded = cv2.imencode(".jpg", blurred, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
    if not ok:
        return blurred
    return cv2.imdecode(encoded, cv2.IMREAD_COLOR)
