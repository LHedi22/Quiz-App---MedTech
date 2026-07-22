"""Subtask 4.1 (QR-after-embed) and 4.2 (PDF layout) DoD checks."""

import io
import uuid

import fitz
import pytest
from PIL import Image

from app.models.version import QuestionForRender, VersionForRender
from app.services import pdf_gen
from app.services.pdf_gen import load_template, render_version_pdf
from app.services.qr import decode_qr


def _make_version(
    num_questions: int, version_number: int = 1
) -> tuple[str, VersionForRender, dict]:
    questions = []
    option_order = {}
    question_order = []
    for i in range(num_questions):
        qid = uuid.uuid4()
        question_order.append(qid)
        options = [f"Option {j} for Q{i + 1}" for j in range(4)]
        questions.append(
            QuestionForRender(id=qid, text=f"Question {i + 1} text goes here?", options=options)
        )
        option_order[str(qid)] = [2, 0, 3, 1]

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


def _crop_qr(page: fitz.Page, template: dict, dpi: int = 200) -> bytes:
    scale = dpi / 72.0
    box = template["qr_box"]
    page_h = template["page_height_pt"]

    pix = page.get_pixmap(dpi=dpi)
    full_image = Image.open(io.BytesIO(pix.tobytes("png")))

    px_x0 = int(box["x_pt"] * scale)
    px_y0 = int((page_h - box["y_pt"] - box["size_pt"]) * scale)
    px_size = int(box["size_pt"] * scale)
    crop = full_image.crop((px_x0, px_y0, px_x0 + px_size, px_y0 + px_size))

    buf = io.BytesIO()
    crop.save(buf, format="PNG")
    return buf.getvalue()


# ---- Subtask 4.1 DoD: QR survives PDF embedding ----------------------------


def test_qr_decodes_correctly_after_being_embedded_in_rendered_pdf_page():
    quiz_title, version, questions_by_id = _make_version(num_questions=5)
    pdf_bytes = render_version_pdf(quiz_title, version, questions_by_id)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    template = load_template()
    decoded = decode_qr(_crop_qr(doc[0], template))

    assert decoded == version.qr_id


def test_qr_decodes_on_every_page_of_a_multi_page_version():
    template = load_template()
    per_page = template["questions_per_page"]
    quiz_title, version, questions_by_id = _make_version(num_questions=per_page * 2 + 3)
    pdf_bytes = render_version_pdf(quiz_title, version, questions_by_id)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    assert doc.page_count == 3

    for page in doc:
        assert decode_qr(_crop_qr(page, template)) == version.qr_id


# ---- Subtask 4.2 DoD: layout -----------------------------------------------


def test_page_count_and_question_count_match_expectations_for_10q_4opt_quiz():
    quiz_title, version, questions_by_id = _make_version(num_questions=10)
    pdf_bytes = render_version_pdf(quiz_title, version, questions_by_id)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    template = load_template()
    assert template["questions_per_page"] >= 10, "test assumes a single page for 10 questions"
    assert doc.page_count == 1

    text = doc[0].get_text()
    for i, qid in enumerate(version.question_order, start=1):
        question = questions_by_id[qid]
        assert f"{i}. {question.text}" in text
        for option_text in question.options:
            assert option_text in text
        for label in "ABCD":
            assert label in text


def test_question_count_per_page_matches_questions_per_page_config():
    template = load_template()
    per_page = template["questions_per_page"]
    quiz_title, version, questions_by_id = _make_version(num_questions=per_page + 4)
    pdf_bytes = render_version_pdf(quiz_title, version, questions_by_id)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    assert doc.page_count == 2

    page1_text = doc[0].get_text()
    page2_text = doc[1].get_text()
    assert f"{per_page}. " in page1_text
    assert f"{per_page + 1}. " not in page1_text
    assert f"{per_page + 1}. " in page2_text


def test_qr_position_is_pixel_identical_across_three_sample_pdfs():
    template = load_template()
    bboxes = []
    for version_number in range(1, 4):
        quiz_title, version, questions_by_id = _make_version(
            num_questions=6, version_number=version_number
        )
        pdf_bytes = render_version_pdf(quiz_title, version, questions_by_id)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        images = doc[0].get_image_info()
        # the QR is the only embedded raster image on the page
        assert len(images) == 1
        bboxes.append(images[0]["bbox"])

    assert len(set(bboxes)) == 1, f"QR bounding box moved across versions: {bboxes}"

    box = template["qr_box"]
    expected_bbox = (
        box["x_pt"],
        template["page_height_pt"] - box["y_pt"] - box["size_pt"],
        box["x_pt"] + box["size_pt"],
        template["page_height_pt"] - box["y_pt"],
    )
    assert bboxes[0] == pytest.approx(expected_bbox, abs=0.1)


def test_bubble_and_qr_geometry_is_read_from_the_template_config_not_hardcoded(monkeypatch):
    """Proves render_version_pdf consults app/config/pdf_template.json for
    positioning rather than baking coordinates into the rendering code: moving
    the QR box in the config must move it in the rendered output."""
    base_template = dict(load_template())
    moved_template = dict(base_template)
    moved_template["qr_box"] = {"x_pt": 100, "y_pt": 100, "size_pt": 50}

    monkeypatch.setattr(pdf_gen, "load_template", lambda: moved_template)

    quiz_title, version, questions_by_id = _make_version(num_questions=3)
    pdf_bytes = render_version_pdf(quiz_title, version, questions_by_id)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    bbox = doc[0].get_image_info()[0]["bbox"]
    expected_bbox = (100.0, 792 - 100 - 50, 100.0 + 50, 792 - 100)
    assert bbox == pytest.approx(expected_bbox, abs=0.1)


def test_template_config_documents_bubble_grid_coordinates():
    template = load_template()
    required_keys = {
        "first_question_y_pt",
        "row_height_pt",
        "questions_per_page",
        "option_start_x_pt",
        "option_spacing_x_pt",
        "bubble_dy_pt",
        "bubble_radius_pt",
    }
    assert required_keys.issubset(template.keys())


def test_render_is_deterministic_for_identical_input():
    quiz_title, version, questions_by_id = _make_version(num_questions=4)
    first = render_version_pdf(quiz_title, version, questions_by_id)
    second = render_version_pdf(quiz_title, version, questions_by_id)
    assert first == second
