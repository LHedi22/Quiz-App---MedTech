"""Renders a version into a print-ready, multi-page PDF bubble sheet.

Layout geometry (page size, QR box, question row grid, bubble positions) is
not hardcoded here — it is loaded from `app/config/pdf_template.json`, the
single source of truth also consulted by later OMR alignment code (Phase 5/6).

Design decision (documented per Phase 4.2's DoD): the QR code is re-embedded,
identically positioned, on *every* page of a multi-page version rather than
only the first page. A professor's stack of papers can be scanned in any
order, and individual pages can be separated from the rest of the packet;
requiring only page 1 to carry identification would make every other page
unscoreable on its own.
"""

from __future__ import annotations

import io
import json
from functools import lru_cache
from pathlib import Path
from string import ascii_uppercase
from uuid import UUID

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.models.version import QuestionForRender, VersionForRender
from app.services.geometry import bubble_center_pt, fiducial_positions_pt
from app.services.qr import generate_qr

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "config" / "pdf_template.json"


@lru_cache(maxsize=1)
def load_template() -> dict:
    return json.loads(TEMPLATE_PATH.read_text())


def _bubble_center(template: dict, row_index: int, option_index: int) -> tuple[float, float]:
    return bubble_center_pt(template, row_index, option_index)


def _draw_fiducials(c: canvas.Canvas, template: dict) -> None:
    """Solid black corner squares consumed by Phase 5 OMR alignment. Drawn as
    vector shapes (not raster images) so they don't disturb the "QR is the
    only embedded raster image on the page" assumption Phase 4's tests rely
    on."""
    size = template["fiducials"]["size_pt"]
    c.setFillColorRGB(0, 0, 0)
    for x, y in fiducial_positions_pt(template).values():
        c.rect(x, y, size, size, fill=1, stroke=0)


def _draw_header(
    c: canvas.Canvas,
    template: dict,
    quiz_title: str,
    version_number: int,
    page_no: int,
    page_count: int,
) -> None:
    header = template["header"]
    c.setFont("Helvetica-Bold", header["title_font_size"])
    c.drawString(header["title_x_pt"], header["title_y_pt"], quiz_title)
    c.setFont("Helvetica", header["meta_font_size"])
    c.drawString(
        header["meta_x_pt"],
        header["meta_y_pt"],
        f"Version {version_number} - Page {page_no} of {page_count}",
    )


def _draw_qr(c: canvas.Canvas, template: dict, qr_png: bytes) -> None:
    box = template["qr_box"]
    image = ImageReader(io.BytesIO(qr_png))
    c.drawImage(
        image,
        box["x_pt"],
        box["y_pt"],
        width=box["size_pt"],
        height=box["size_pt"],
        preserveAspectRatio=True,
        mask="auto",
    )


def _draw_question(
    c: canvas.Canvas,
    template: dict,
    row_index: int,
    question_no: int,
    question: QuestionForRender,
    shuffled_option_indices: list[int],
) -> None:
    row_y = template["first_question_y_pt"] - row_index * template["row_height_pt"]

    c.setFont("Helvetica", template["question_text_font_size"])
    c.drawString(
        template["question_text_x_pt"],
        row_y + template["question_text_dy_pt"],
        f"{question_no}. {question.text}",
    )

    for option_index, canonical_index in enumerate(shuffled_option_indices):
        label = ascii_uppercase[option_index]
        option_text = question.options[canonical_index]
        x, y = _bubble_center(template, row_index, option_index)

        c.circle(x, y, template["bubble_radius_pt"], stroke=1, fill=0)
        c.setFont("Helvetica-Bold", template["option_label_font_size"])
        c.drawRightString(x + template["bubble_label_dx_pt"], y - 3, label)
        c.setFont("Helvetica", template["option_label_font_size"])
        c.drawString(x + template["bubble_radius_pt"] + 4, y - 3, option_text)


def render_version_pdf(
    quiz_title: str,
    version: VersionForRender,
    questions_by_id: dict[UUID, QuestionForRender],
) -> bytes:
    """Render `version`'s shuffled questions/options into a PDF, QR on every page."""
    template = load_template()
    qr_png = generate_qr(version.qr_id)

    ordered_questions = [questions_by_id[qid] for qid in version.question_order]
    per_page = template["questions_per_page"]
    pages = [
        ordered_questions[i : i + per_page] for i in range(0, len(ordered_questions), per_page)
    ] or [[]]

    buffer = io.BytesIO()
    # invariant=1 strips ReportLab's default embedded creation timestamp/doc-id
    # so identical inputs always produce byte-identical PDFs (relied on by tests
    # and by the storage layer's idempotency check).
    c = canvas.Canvas(buffer, pagesize=LETTER, invariant=1)

    for page_index, page_questions in enumerate(pages):
        _draw_header(c, template, quiz_title, version.version_number, page_index + 1, len(pages))
        _draw_qr(c, template, qr_png)
        _draw_fiducials(c, template)
        for row_index, question in enumerate(page_questions):
            question_no = page_index * per_page + row_index + 1
            shuffled_option_indices = version.option_order[str(question.id)]
            _draw_question(c, template, row_index, question_no, question, shuffled_option_indices)
        c.showPage()

    c.save()
    return buffer.getvalue()
