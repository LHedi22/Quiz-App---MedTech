"""Subtask 9.2: full unhappy-path E2E test.

Same real-HTTP, real-Supabase-stack flow as test_e2e_happy_path.py, but each
test injects exactly one of the three specified failures at its natural
point in the flow and asserts the exact resulting system state - real DB
rows, not just "the request didn't 500":

1. A malformed Excel row -> structured 422 error, zero questions written.
2. An ambiguous bubble mark -> needs_review, with exactly that question's
   answer flagged (confidence below the classifier's threshold, unscored).
3. An unreadable QR code -> a distinct qr_unreadable signal, zero
   submissions ever created.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import cv2
import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from app.db import DATABASE_URL
from app.main import app
from app.ml.omr.classify import CONFIDENCE_THRESHOLD
from app.services.geometry import bubble_center_pt, pdf_point_to_pixel, qr_box_pixel_rect
from app.services.pdf_gen import load_template
from tests.omr_test_utils import render_page_rgb
from tests.test_quizzes_endpoint import auth_headers, create_auth_user_and_token

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "excel"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DPI = 200
NUM_OPTIONS = 4


def _db_reachable() -> bool:
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2):
            return True
    except psycopg.OperationalError:
        return False


def _supabase_reachable() -> bool:
    try:
        httpx.get("http://127.0.0.1:54341/auth/v1/health", timeout=2.0)
        return True
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(
    not (_db_reachable() and _supabase_reachable()),
    reason="local Supabase/Postgres stack not reachable (run `supabase start` in /backend)",
)

client = TestClient(app)


def run_sql(sql: str) -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)


@pytest.fixture
def professor():
    suffix = uuid.uuid4().hex[:8]
    email = f"e2e-unhappy-{suffix}@example.com"
    user_id, token = create_auth_user_and_token(email)
    yield {"user_id": user_id, "token": token}
    run_sql(f"""
        delete from submissions where version_id in
            (select id from versions where quiz_id in
                (select id from quizzes where owner_id = '{user_id}'));
        delete from quizzes where owner_id = '{user_id}';
        delete from users where id = '{user_id}';
        delete from auth.users where id = '{user_id}';
        """)


def _question_count(quiz_id: str) -> int:
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from questions where quiz_id = %s", (quiz_id,))
            return cur.fetchone()[0]


def test_malformed_excel_row_produces_structured_error_and_writes_no_questions(professor):
    create = client.post(
        "/quizzes",
        json={"title": "E2E Unhappy - malformed excel"},
        headers=auth_headers(professor["token"]),
    )
    assert create.status_code == 201, create.text
    quiz_id = create.json()["id"]

    # missing_answer.xlsx: row 2 is valid, row 3 has an empty correct_option
    # cell - exactly one malformed row, per the DoD's own phrasing.
    with open(FIXTURES_DIR / "missing_answer.xlsx", "rb") as f:
        upload = client.post(
            f"/quizzes/{quiz_id}/upload",
            files={"file": ("missing_answer.xlsx", f, XLSX_CONTENT_TYPE)},
            headers=auth_headers(professor["token"]),
        )

    assert upload.status_code == 422, upload.text
    errors = upload.json()["detail"]["errors"]
    assert errors == [
        {
            "row_number": 3,
            "messages": ["correct_option must be exactly one of A/B/C/D, got ''"],
        }
    ]
    assert _question_count(quiz_id) == 0, "a rejected upload must write zero question rows"


def _fetch_version_mapping(version_id: str) -> dict:
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select question_order, option_order from versions where id = %s",
                (version_id,),
            )
            question_order, option_order = cur.fetchone()
    return {"question_order": question_order, "option_order": option_order}


def _fetch_questions_by_id(quiz_id: str) -> dict:
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select id, order_index, correct_option from questions where quiz_id = %s",
                (quiz_id,),
            )
            rows = cur.fetchall()
    return {str(row[0]): {"order_index": row[1], "correct_option": row[2]} for row in rows}


def _mark_bubble_filled(image, template: dict, row_index: int, option_index: int) -> None:
    x_pt, y_pt = bubble_center_pt(template, row_index, option_index)
    px, py = pdf_point_to_pixel(x_pt, y_pt, template["page_height_pt"], DPI)
    radius_px = int(round(template["bubble_radius_pt"] * DPI / 72.0 * 0.8))
    cv2.circle(image, (int(round(px)), int(round(py))), radius_px, (0, 0, 0), thickness=-1)


def _mark_bubble_ambiguous(image, template: dict, row_index: int, option_index: int) -> None:
    """A partial (~50%-area) fill - calibrated against the real trained
    classifier (not assumed from the synthetic training-data ranges) to
    land reliably in "ambiguous" territory, comfortably clear of both the
    empty and confidently-filled sides of CONFIDENCE_THRESHOLD. See
    scratch calibration: area_fraction=0.50 -> confidence ~0.80, vs. 0.60
    already reads as confidently "filled"."""
    x_pt, y_pt = bubble_center_pt(template, row_index, option_index)
    px, py = pdf_point_to_pixel(x_pt, y_pt, template["page_height_pt"], DPI)
    full_radius_px = template["bubble_radius_pt"] * DPI / 72.0
    fill_radius_px = int(round(full_radius_px * (0.50**0.5)))
    cv2.circle(image, (int(round(px)), int(round(py))), fill_radius_px, (0, 0, 0), thickness=-1)


def _page_to_upload_bytes(page_rgb) -> bytes:
    bgr = cv2.cvtColor(page_rgb, cv2.COLOR_RGB2BGR)
    ok, encoded = cv2.imencode(".png", bgr)
    assert ok
    return encoded.tobytes()


def _download_and_rasterize_version_pdf(version_id: str, token: str):
    response = client.get(f"/versions/{version_id}/pdf", headers=auth_headers(token))
    assert response.status_code == 200, response.text
    signed_url = response.json()["url"]
    pdf_bytes = httpx.get(signed_url).content
    return render_page_rgb(pdf_bytes, dpi=DPI)


@pytest.fixture
def quiz_with_one_version(professor):
    create = client.post(
        "/quizzes",
        json={"title": "E2E Unhappy - scan failures"},
        headers=auth_headers(professor["token"]),
    )
    quiz_id = create.json()["id"]
    with open(FIXTURES_DIR / "valid.xlsx", "rb") as f:
        upload = client.post(
            f"/quizzes/{quiz_id}/upload",
            files={"file": ("valid.xlsx", f, XLSX_CONTENT_TYPE)},
            headers=auth_headers(professor["token"]),
        )
    assert upload.status_code == 201, upload.text

    gen = client.post(
        f"/quizzes/{quiz_id}/versions",
        json={"count": 1},
        headers=auth_headers(professor["token"]),
    )
    assert gen.status_code == 201, gen.text

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("select id from versions where quiz_id = %s", (quiz_id,))
            version_id = str(cur.fetchone()[0])

    return {"quiz_id": quiz_id, "version_id": version_id, "token": professor["token"]}


def test_ambiguous_bubble_scan_needs_review_with_exact_flagged_question(quiz_with_one_version):
    quiz_id = quiz_with_one_version["quiz_id"]
    version_id = quiz_with_one_version["version_id"]

    mapping = _fetch_version_mapping(version_id)
    questions_by_id = _fetch_questions_by_id(quiz_id)
    template = load_template()
    page_rgb = _download_and_rasterize_version_pdf(version_id, quiz_with_one_version["token"])

    # Row 1 (0-based) gets the deliberately ambiguous mark; every other row
    # is marked correctly, so exactly one answer should end up flagged.
    ambiguous_row_index = 1
    for row_index, qid in enumerate(mapping["question_order"]):
        question = questions_by_id[str(qid)]
        canonical_index = ord(question["correct_option"].upper()) - ord("A")
        permutation = mapping["option_order"][str(qid)]
        correct_shuffled_pos = permutation.index(canonical_index)
        if row_index == ambiguous_row_index:
            _mark_bubble_ambiguous(page_rgb, template, row_index, correct_shuffled_pos)
        else:
            _mark_bubble_filled(page_rgb, template, row_index, correct_shuffled_pos)

    expected_flagged_qno = questions_by_id[str(mapping["question_order"][ambiguous_row_index])][
        "order_index"
    ]

    response = client.post(
        "/scan",
        files={"file": ("scan.png", _page_to_upload_bytes(page_rgb), "image/png")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "needs_review"
    assert body["total_score"] is None
    assert body["flagged_question_numbers"] == [expected_flagged_qno]

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select status, total_score from submissions where id = %s",
                (body["submission_id"],),
            )
            status, total_score = cur.fetchone()
            cur.execute(
                "select question_no, detected_option, confidence, flagged, correct, score "
                "from answers where submission_id = %s order by question_no",
                (body["submission_id"],),
            )
            cols = [c.name for c in cur.description]
            answers = [dict(zip(cols, row)) for row in cur.fetchall()]

    assert status == "needs_review"
    assert total_score is None
    assert len(answers) == 3
    flagged = [a for a in answers if a["flagged"]]
    assert len(flagged) == 1
    assert flagged[0]["question_no"] == expected_flagged_qno
    assert flagged[0]["detected_option"] is None
    assert flagged[0]["correct"] is None
    assert flagged[0]["score"] is None
    assert flagged[0]["confidence"] < CONFIDENCE_THRESHOLD
    for answer in answers:
        if not answer["flagged"]:
            assert answer["correct"] is True
            assert answer["score"] == 1.0


def test_unreadable_qr_scan_returns_distinct_signal_and_creates_no_submission(
    quiz_with_one_version,
):
    version_id = quiz_with_one_version["version_id"]
    template = load_template()
    page_rgb = _download_and_rasterize_version_pdf(version_id, quiz_with_one_version["token"])

    x0, y0, x1, y1 = qr_box_pixel_rect(template, DPI)
    page_rgb[y0:y1, x0:x1] = 255  # whiteout the QR box entirely -> undecodable

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from submissions s join versions v on v.id = s.version_id "
                "where v.id = %s",
                (version_id,),
            )
            before = cur.fetchone()[0]

    response = client.post(
        "/scan",
        files={"file": ("scan.png", _page_to_upload_bytes(page_rgb), "image/png")},
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["error"] == "qr_unreadable"

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from submissions s join versions v on v.id = s.version_id "
                "where v.id = %s",
                (version_id,),
            )
            after = cur.fetchone()[0]
    assert after == before == 0, "an unreadable-QR scan must never create a submission row"
