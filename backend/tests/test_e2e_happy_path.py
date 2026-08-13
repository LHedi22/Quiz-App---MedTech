"""Subtask 9.1: full happy-path E2E test.

Excel upload -> version generation -> PDF download -> synthetic scan of each
version's real, independently-shuffled PDF -> finalized submissions with the
mathematically correct score. Every step goes through the real HTTP API
against the real local Supabase + Postgres + Storage stack (the project's
established "real deployment" for every phase so far - see PROGRESS.md);
nothing about the pipeline itself is mocked.

Two of the three versions are filled entirely with the correct answers
(expected score = 3.0, the max for this 3-question fixture); the third has
exactly one question deliberately marked wrong (expected score = 2.0), so
this test actually proves the full excel->shuffle->pdf->scan->score chain
produces *differentiated*, correct scores per version - not just "any full
sheet of correct marks yields the max", which could pass even if the
question/option un-shuffle were subtly broken in a way that happened to be
symmetric.
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
from app.services.geometry import bubble_center_pt, pdf_point_to_pixel
from app.services.pdf_gen import load_template
from tests.omr_test_utils import render_page_rgb
from tests.test_quizzes_endpoint import auth_headers, create_auth_user_and_token

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "excel"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DPI = 200

# Ground truth for tests/fixtures/excel/valid.xlsx (see generate_fixtures.py):
# 3 questions, correct answers B, C, B (row 3's "b" is lowercase, verified
# case-insensitive by test_parsing.py already).
VALID_XLSX_CORRECT_OPTIONS = ["B", "C", "B"]
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
    email = f"e2e-happy-{suffix}@example.com"
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


def _mark_bubble(image, template: dict, row_index: int, option_index: int) -> None:
    x_pt, y_pt = bubble_center_pt(template, row_index, option_index)
    px, py = pdf_point_to_pixel(x_pt, y_pt, template["page_height_pt"], DPI)
    radius_px = int(round(template["bubble_radius_pt"] * DPI / 72.0 * 0.8))
    cv2.circle(image, (int(round(px)), int(round(py))), radius_px, (0, 0, 0), thickness=-1)


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


def _scan_version(
    quiz_id: str, version_id: str, wrong_question_order_index: int | None, token: str
):
    """Renders+marks version_id's real PDF and POSTs it through /scan.
    If wrong_question_order_index is given, that row (0-based position within
    question_order) is marked with an *incorrect* option instead of the
    correct one."""
    mapping = _fetch_version_mapping(version_id)
    questions_by_id = _fetch_questions_by_id(quiz_id)
    template = load_template()
    page_rgb = _download_and_rasterize_version_pdf(version_id, token)

    for row_index, qid in enumerate(mapping["question_order"]):
        question = questions_by_id[str(qid)]
        canonical_index = ord(question["correct_option"].upper()) - ord("A")
        permutation = mapping["option_order"][str(qid)]
        correct_shuffled_pos = permutation.index(canonical_index)

        if row_index == wrong_question_order_index:
            shuffled_pos = (correct_shuffled_pos + 1) % NUM_OPTIONS
        else:
            shuffled_pos = correct_shuffled_pos
        _mark_bubble(page_rgb, template, row_index, shuffled_pos)

    response = client.post(
        "/scan",
        files={"file": ("scan.png", _page_to_upload_bytes(page_rgb), "image/png")},
        params={"student_id": f"student-{version_id}"},
    )
    return response


def _fetch_submission_db_state(submission_id: str) -> dict:
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select status, total_score from submissions where id = %s", (submission_id,)
            )
            status, total_score = cur.fetchone()
            cur.execute(
                "select question_no, correct, score, flagged from answers "
                "where submission_id = %s order by question_no",
                (submission_id,),
            )
            cols = [c.name for c in cur.description]
            answers = [dict(zip(cols, row)) for row in cur.fetchall()]
    return {"status": status, "total_score": total_score, "answers": answers}


def test_full_happy_path_excel_to_three_finalized_correctly_scored_submissions(professor):
    # 1. Create quiz.
    create = client.post(
        "/quizzes", json={"title": "E2E Happy Path Quiz"}, headers=auth_headers(professor["token"])
    )
    assert create.status_code == 201, create.text
    quiz_id = create.json()["id"]

    # 2. Upload real Excel fixture.
    with open(FIXTURES_DIR / "valid.xlsx", "rb") as f:
        upload = client.post(
            f"/quizzes/{quiz_id}/upload",
            files={"file": ("valid.xlsx", f, XLSX_CONTENT_TYPE)},
            headers=auth_headers(professor["token"]),
        )
    assert upload.status_code == 201, upload.text
    assert upload.json()["questions_inserted"] == 3

    # 3. Generate 3 versions.
    gen = client.post(
        f"/quizzes/{quiz_id}/versions",
        json={"count": 3},
        headers=auth_headers(professor["token"]),
    )
    assert gen.status_code == 201, gen.text
    assert gen.json()["versions_created"] == 3

    versions = client.get(f"/quizzes/{quiz_id}/versions", headers=auth_headers(professor["token"]))
    assert versions.status_code == 200
    version_ids = [v["id"] for v in versions.json()]
    assert len(version_ids) == 3

    # 4/5/6. Download each version's PDF, simulate scanning it, assert
    # finalization with the mathematically correct score.
    # Versions 0 and 2: every question answered correctly -> max score 3.0.
    # Version 1: question at question_order position 0 deliberately marked
    # wrong -> exactly 2.0.
    expectations = {
        version_ids[0]: (None, 3.0),
        version_ids[1]: (0, 2.0),
        version_ids[2]: (None, 3.0),
    }

    submission_ids = []
    for version_id, (wrong_index, expected_score) in expectations.items():
        response = _scan_version(quiz_id, version_id, wrong_index, professor["token"])
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["status"] == "finalized", body
        assert body["total_score"] == expected_score, (version_id, body)
        assert body["flagged_question_numbers"] == []
        submission_ids.append(body["submission_id"])

        db_state = _fetch_submission_db_state(body["submission_id"])
        assert db_state["status"] == "finalized"
        assert db_state["total_score"] == expected_score
        assert len(db_state["answers"]) == 3
        assert all(not a["flagged"] for a in db_state["answers"])
        correct_count = sum(1 for a in db_state["answers"] if a["correct"])
        assert correct_count == int(expected_score)

    assert len(set(submission_ids)) == 3, "each scan must create its own distinct submission"
