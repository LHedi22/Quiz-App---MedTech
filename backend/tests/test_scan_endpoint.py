"""Subtask 6.4: POST /scan, GET /submissions, PATCH /submissions/{id}/answers/{id}.

Builds a realistic synthetic scanned image the same way the rest of the
Phase 5 OMR test suite does (tests/omr_test_utils.py): render a real version
PDF via the Phase 4 renderer, rasterize it with PyMuPDF, draw pencil-style
filled dots at specific bubble positions, then run it through the actual
`/scan` HTTP endpoint end-to-end - no mocking of alignment, extraction, or
classification.
"""

from __future__ import annotations

import io
import uuid

import cv2
import numpy as np
import psycopg
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from psycopg.types.json import Json

from app.db import DATABASE_URL
from app.main import app
from app.ml.omr.name_ocr import NameDetectionResult
from app.models.scoring import ScoredAnswer, ScoringResult
from app.services import submissions as submissions_service
from app.services.geometry import bubble_center_pt, pdf_point_to_pixel
from app.services.pdf_gen import load_template, render_version_pdf
from app.services.qr import generate_qr
from tests.omr_test_utils import render_page_rgb, rotate_with_padding, write_name_on_page
from tests.test_quizzes_endpoint import auth_headers, create_auth_user_and_token


def _db_reachable() -> bool:
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2):
            return True
    except psycopg.OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    not _db_reachable(),
    reason="local Postgres not reachable (run `supabase start` in /backend)",
)

client = TestClient(app)
DPI = 200


def run_sql(sql: str) -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)


def _mark_bubble_filled(image, template: dict, row_index: int, option_index: int) -> None:
    x_pt, y_pt = bubble_center_pt(template, row_index, option_index)
    px, py = pdf_point_to_pixel(x_pt, y_pt, template["page_height_pt"], DPI)
    radius_px = int(round(template["bubble_radius_pt"] * DPI / 72.0 * 0.8))
    cv2.circle(image, (int(round(px)), int(round(py))), radius_px, (0, 0, 0), thickness=-1)


def _page_to_upload_bytes(page_rgb) -> bytes:
    bgr = cv2.cvtColor(page_rgb, cv2.COLOR_RGB2BGR)
    ok, encoded = cv2.imencode(".png", bgr)
    assert ok
    return encoded.tobytes()


@pytest.fixture
def seeded_quiz():
    """A real quiz + version persisted to the DB with a fully known,
    non-identity question_order/option_order mapping, so expected scores can
    be hand-derived. 4 questions, 4 options each - the Excel-format option
    count `/scan` assumes."""
    # A real Supabase Auth user (not just a raw public.users row) is needed
    # so the PATCH /submissions/.../answers/... test below - which now
    # requires an owning professor's bearer token per the ownership check
    # added alongside Phase 7 - can actually authenticate as this quiz's
    # owner.
    email = f"scan-test-{uuid.uuid4().hex[:8]}@example.com"
    user_id_str, token = create_auth_user_and_token(email)
    user_id = uuid.UUID(user_id_str)
    quiz_id = uuid.uuid4()
    run_sql(f"""
        insert into users (id, email) values ('{user_id}', '{email}');
        insert into quizzes (id, owner_id, title)
          values ('{quiz_id}', '{user_id}', 'Scan test quiz');
        """)

    # order_index 1..4, correct options A/B/C/D respectively.
    question_ids = [uuid.uuid4() for _ in range(4)]
    correct_options = ["A", "B", "C", "D"]
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            for i, (qid, correct) in enumerate(zip(question_ids, correct_options)):
                cur.execute(
                    """
                    insert into questions (id, quiz_id, text, options, correct_option, order_index)
                    values (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(qid),
                        str(quiz_id),
                        f"Question {i + 1}?",
                        Json([f"Opt {j}" for j in range(4)]),
                        correct,
                        i + 1,
                    ),
                )
        conn.commit()

    # Non-identity question order (reverse) and a distinct non-identity
    # option-order permutation per question.
    question_order = list(reversed(question_ids))
    option_permutations = [[1, 2, 3, 0], [2, 3, 0, 1], [3, 0, 1, 2], [0, 3, 2, 1]]
    option_order = {str(qid): perm for qid, perm in zip(question_ids, option_permutations)}
    qr_id = f"scan-test-{uuid.uuid4()}"
    version_id = uuid.uuid4()
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into versions
                    (id, quiz_id, version_number, qr_id, question_order, option_order)
                values (%s, %s, 1, %s, %s, %s)
                """,
                (
                    str(version_id),
                    str(quiz_id),
                    qr_id,
                    Json([str(qid) for qid in question_order]),
                    Json(option_order),
                ),
            )
        conn.commit()

    questions_by_order_index = {
        i + 1: {"id": qid, "correct_option": correct}
        for i, (qid, correct) in enumerate(zip(question_ids, correct_options))
    }

    yield {
        "quiz_id": quiz_id,
        "version_id": version_id,
        "qr_id": qr_id,
        "question_order": question_order,
        "option_order": option_order,
        "questions_by_order_index": questions_by_order_index,
        "token": token,
    }

    # submissions.version_id has no ON DELETE CASCADE (CLAUDE.md Section 4),
    # so any submissions created against this quiz's version (answers cascade
    # from submissions) must be cleared before the quiz/version themselves.
    run_sql(f"""
        delete from submissions where version_id = '{version_id}';
        delete from quizzes where id = '{quiz_id}';
        delete from users where id = '{user_id}';
        delete from auth.users where id = '{user_id}';
        """)


def _correct_shuffled_position(seeded_quiz, question_id: uuid.UUID) -> int:
    correct_option = next(
        q["correct_option"]
        for q in seeded_quiz["questions_by_order_index"].values()
        if q["id"] == question_id
    )
    canonical_index = ord(correct_option) - ord("A")
    return seeded_quiz["option_order"][str(question_id)].index(canonical_index)


def _render_and_rasterize(seeded_quiz):
    from app.models.version import QuestionForRender, VersionForRender

    questions_by_id = {
        q["id"]: QuestionForRender(
            id=q["id"], text=f"Q{i}?", options=[f"Opt {j}" for j in range(4)]
        )
        for i, q in seeded_quiz["questions_by_order_index"].items()
    }
    version = VersionForRender(
        id=seeded_quiz["version_id"],
        quiz_id=seeded_quiz["quiz_id"],
        version_number=1,
        qr_id=seeded_quiz["qr_id"],
        question_order=seeded_quiz["question_order"],
        option_order=seeded_quiz["option_order"],
    )
    pdf_bytes = render_version_pdf("Scan test quiz", version, questions_by_id)
    return render_page_rgb(pdf_bytes, dpi=DPI)


def _fetch_submission(submission_id: str) -> dict:
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select status, total_score, student_name, name_flagged "
                "from submissions where id = %s",
                (submission_id,),
            )
            status, total_score, student_name, name_flagged = cur.fetchone()
            cur.execute(
                "select question_no, detected_option, confidence, flagged, correct, score, id "
                "from answers where submission_id = %s order by question_no",
                (submission_id,),
            )
            cols = [c.name for c in cur.description]
            answers = [dict(zip(cols, row)) for row in cur.fetchall()]
    return {
        "status": status,
        "total_score": total_score,
        "student_name": student_name,
        "name_flagged": name_flagged,
        "answers": answers,
    }


def test_scan_all_correct_finalizes_with_correct_db_state(seeded_quiz):
    template = load_template()
    page_rgb = _render_and_rasterize(seeded_quiz)
    write_name_on_page(page_rgb, template, "JOHN SMITH", dpi=DPI)

    for row_index, qid in enumerate(seeded_quiz["question_order"]):
        shuffled_pos = _correct_shuffled_position(seeded_quiz, qid)
        _mark_bubble_filled(page_rgb, template, row_index, shuffled_pos)

    response = client.post(
        "/scan",
        files={"file": ("scan.png", _page_to_upload_bytes(page_rgb), "image/png")},
        params={"student_id": "student-42"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "finalized"
    assert body["total_score"] == 4.0
    assert body["flagged_question_numbers"] == []
    assert body["name_flagged"] is False
    assert "SMITH" in body["student_name"].upper()

    db_state = _fetch_submission(body["submission_id"])
    assert db_state["status"] == "finalized"
    assert db_state["total_score"] == 4.0
    assert len(db_state["answers"]) == 4
    for answer in db_state["answers"]:
        assert answer["flagged"] is False
        assert answer["correct"] is True
        assert answer["score"] == 1.0


def test_scan_from_a_rotated_camera_style_photo_still_decodes_and_scores(seeded_quiz):
    """A live browser/phone camera capture is never pixel-perfect axis-aligned
    like the rest of this file's synthetic fixtures - it's rotated/skewed by
    however the professor was holding the device, which is exactly what
    `align_page`'s fiducial homography exists to correct (Subtask 5.1). The
    QR box's position is only valid post-alignment, so decoding must happen
    against the warped image, not the raw upload - otherwise a real photo's
    QR code is essentially never where `qr_box_pixel_rect` expects it and
    every genuine camera scan 422s as qr_unreadable (see Phase 7c web
    scanning: this is what a live professor hits every time they submit)."""
    template = load_template()
    page_rgb = _render_and_rasterize(seeded_quiz)
    write_name_on_page(page_rgb, template, "JOHN SMITH", dpi=DPI)
    for row_index, qid in enumerate(seeded_quiz["question_order"]):
        shuffled_pos = _correct_shuffled_position(seeded_quiz, qid)
        _mark_bubble_filled(page_rgb, template, row_index, shuffled_pos)

    rotated, _forward_matrix = rotate_with_padding(page_rgb, angle_deg=8)

    response = client.post(
        "/scan", files={"file": ("scan.png", _page_to_upload_bytes(rotated), "image/png")}
    )

    # The point of this test is that the pipeline reaches scoring at all
    # instead of 422ing as qr_unreadable - not exact classifier confidence
    # under rotation-warp interpolation, which can plausibly soften one
    # bubble's edges enough to dip below the confidence threshold. Either
    # outcome here proves QR decode + alignment + scoring all succeeded.
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] in ("finalized", "needs_review")
    assert len(body["flagged_question_numbers"]) <= 1


def _scan_with_one_multi_mark(seeded_quiz) -> tuple[dict, int]:
    """Scans a page with every question correctly single-marked except row 1,
    which gets two marks. Returns the /scan response body and the canonical
    question number expected to be the sole flagged answer."""
    template = load_template()
    page_rgb = _render_and_rasterize(seeded_quiz)
    write_name_on_page(page_rgb, template, "JANE DOE", dpi=DPI)

    for row_index, qid in enumerate(seeded_quiz["question_order"]):
        shuffled_pos = _correct_shuffled_position(seeded_quiz, qid)
        _mark_bubble_filled(page_rgb, template, row_index, shuffled_pos)
    # Add a second mark on row 1 -> multi-mark, must flag exactly that question.
    second_option = (
        _correct_shuffled_position(seeded_quiz, seeded_quiz["question_order"][1]) + 1
    ) % 4
    _mark_bubble_filled(page_rgb, template, 1, second_option)

    response = client.post(
        "/scan", files={"file": ("scan.png", _page_to_upload_bytes(page_rgb), "image/png")}
    )
    assert response.status_code == 201, response.text

    row1_question_id = seeded_quiz["question_order"][1]
    expected_flagged_no = next(
        no
        for no, q in seeded_quiz["questions_by_order_index"].items()
        if q["id"] == row1_question_id
    )
    return response.json(), expected_flagged_no


def test_scan_with_one_multi_mark_question_needs_review(seeded_quiz):
    body, expected_flagged_no = _scan_with_one_multi_mark(seeded_quiz)

    assert body["status"] == "needs_review"
    assert body["total_score"] is None
    assert body["flagged_question_numbers"] == [expected_flagged_no]

    db_state = _fetch_submission(body["submission_id"])
    assert db_state["status"] == "needs_review"
    assert db_state["total_score"] is None
    flagged_rows = [a for a in db_state["answers"] if a["flagged"]]
    assert len(flagged_rows) == 1
    assert flagged_rows[0]["question_no"] == expected_flagged_no


def test_scan_unreadable_qr_never_creates_submission_or_reaches_scoring(seeded_quiz, monkeypatch):
    from app.routers import scan as scan_router

    called = {"lookup": False}

    def _fail_if_called(*args, **kwargs):
        called["lookup"] = True
        raise AssertionError("lookup_version_by_qr_id must not be called when QR is unreadable")

    monkeypatch.setattr(scan_router, "lookup_version_by_qr_id", _fail_if_called)

    template = load_template()
    page_rgb = _render_and_rasterize(seeded_quiz)
    x0, y0, x1, y1 = _qr_box_pixels(template)
    page_rgb[y0:y1, x0:x1] = 255  # whiteout the QR box entirely

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from submissions s join versions v on v.id = s.version_id "
                "where v.id = %s",
                (str(seeded_quiz["version_id"]),),
            )
            before = cur.fetchone()[0]

    response = client.post(
        "/scan", files={"file": ("scan.png", _page_to_upload_bytes(page_rgb), "image/png")}
    )

    assert response.status_code == 422
    assert response.json()["detail"]["error"] == "qr_unreadable"
    assert called["lookup"] is False

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from submissions s join versions v on v.id = s.version_id "
                "where v.id = %s",
                (str(seeded_quiz["version_id"]),),
            )
            after = cur.fetchone()[0]
    assert after == before, "an unreadable-QR scan must never create a submission row"


def _qr_box_pixels(template):
    from app.services.geometry import qr_box_pixel_rect

    return qr_box_pixel_rect(template, DPI)


def test_scan_qr_from_unknown_version_returns_404_and_creates_no_submission(seeded_quiz):
    unknown_qr_id = f"unregistered-{uuid.uuid4()}"
    qr_png = generate_qr(unknown_qr_id)

    # Splice a real QR for an unregistered id into an otherwise-normal page.
    template = load_template()
    page_rgb = _render_and_rasterize(seeded_quiz)
    x0, y0, x1, y1 = _qr_box_pixels(template)

    qr_img = Image.open(io.BytesIO(qr_png)).convert("RGB").resize((x1 - x0, y1 - y0))
    page_rgb[y0:y1, x0:x1] = np.array(qr_img)

    response = client.post(
        "/scan", files={"file": ("scan.png", _page_to_upload_bytes(page_rgb), "image/png")}
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "version_not_found"
    assert response.json()["detail"]["qr_id"] == unknown_qr_id


def test_professor_manual_correction_updates_score_and_status(seeded_quiz):
    body, expected_flagged_no = _scan_with_one_multi_mark(seeded_quiz)
    submission_id = body["submission_id"]

    db_state = _fetch_submission(submission_id)
    flagged_answer = next(a for a in db_state["answers"] if a["flagged"])
    answer_id = str(flagged_answer["id"])

    correct_option = seeded_quiz["questions_by_order_index"][expected_flagged_no]["correct_option"]

    response = client.patch(
        f"/submissions/{submission_id}/answers/{answer_id}",
        json={"correct_option": correct_option},
        headers=auth_headers(seeded_quiz["token"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "finalized"
    assert body["total_score"] == 4.0
    corrected = next(a for a in body["answers"] if a["id"] == answer_id)
    assert corrected["flagged"] is False
    assert corrected["correct"] is True
    assert corrected["score"] == 1.0

    db_state = _fetch_submission(submission_id)
    assert db_state["status"] == "finalized"
    assert db_state["total_score"] == 4.0
    assert all(not a["flagged"] for a in db_state["answers"])


def test_get_submissions_needs_review_lists_flagged_submission(seeded_quiz):
    body, _ = _scan_with_one_multi_mark(seeded_quiz)
    submission_id = body["submission_id"]
    headers = auth_headers(seeded_quiz["token"])

    response = client.get("/submissions", params={"status": "needs_review"}, headers=headers)
    assert response.status_code == 200
    ids = [row["id"] for row in response.json()]
    assert submission_id in ids

    response_finalized = client.get("/submissions", params={"status": "finalized"}, headers=headers)
    assert response_finalized.status_code == 200
    assert submission_id not in [row["id"] for row in response_finalized.json()]


def test_get_submissions_requires_auth(seeded_quiz):
    _scan_with_one_multi_mark(seeded_quiz)

    response = client.get("/submissions", params={"status": "needs_review"})
    assert response.status_code in (401, 422)


def test_get_submissions_scoped_to_owning_professor(seeded_quiz):
    """Professor B must never see professor A's student rows via this route -
    there is no RLS safety net, so the API-layer owner scoping is the only
    thing enforcing isolation here (CLAUDE.md Section 4)."""
    body, _ = _scan_with_one_multi_mark(seeded_quiz)
    submission_id = body["submission_id"]

    other_email = f"scan-other-{uuid.uuid4().hex[:8]}@example.com"
    other_user_id, other_token = create_auth_user_and_token(other_email)
    try:
        response = client.get(
            "/submissions",
            params={"status": "needs_review"},
            headers=auth_headers(other_token),
        )
        assert response.status_code == 200
        assert submission_id not in [row["id"] for row in response.json()]
    finally:
        run_sql(
            f"delete from users where id = '{other_user_id}';"
            f"delete from auth.users where id = '{other_user_id}';"
        )


# ---- student-name detection DoD ---------------------------------------------


def test_scan_blank_name_needs_review_even_with_all_correct_answers(seeded_quiz):
    """The name confidence gate is independent of the answer confidence gate:
    a submission with every answer correctly, unambiguously marked must still
    route to review if the name field was left blank/illegible."""
    template = load_template()
    page_rgb = _render_and_rasterize(seeded_quiz)
    # deliberately no write_name_on_page call - name field stays blank.

    for row_index, qid in enumerate(seeded_quiz["question_order"]):
        shuffled_pos = _correct_shuffled_position(seeded_quiz, qid)
        _mark_bubble_filled(page_rgb, template, row_index, shuffled_pos)

    response = client.post(
        "/scan", files={"file": ("scan.png", _page_to_upload_bytes(page_rgb), "image/png")}
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name_flagged"] is True
    assert body["status"] == "needs_review"
    assert body["flagged_question_numbers"] == [], "no answer should be flagged, only the name"

    db_state = _fetch_submission(body["submission_id"])
    assert db_state["status"] == "needs_review"
    assert db_state["name_flagged"] is True
    assert all(not a["flagged"] for a in db_state["answers"])


def test_professor_name_correction_finalizes_a_submission_flagged_only_for_name(seeded_quiz):
    template = load_template()
    page_rgb = _render_and_rasterize(seeded_quiz)
    # blank name field -> name_flagged, even though every answer is correct.

    for row_index, qid in enumerate(seeded_quiz["question_order"]):
        shuffled_pos = _correct_shuffled_position(seeded_quiz, qid)
        _mark_bubble_filled(page_rgb, template, row_index, shuffled_pos)

    scan_response = client.post(
        "/scan", files={"file": ("scan.png", _page_to_upload_bytes(page_rgb), "image/png")}
    )
    assert scan_response.status_code == 201, scan_response.text
    submission_id = scan_response.json()["submission_id"]
    assert scan_response.json()["status"] == "needs_review"

    response = client.patch(
        f"/submissions/{submission_id}/name",
        json={"student_name": "Corrected Name"},
        headers=auth_headers(seeded_quiz["token"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["student_name"] == "Corrected Name"
    assert body["name_flagged"] is False
    assert body["status"] == "finalized"
    assert body["total_score"] == 4.0

    db_state = _fetch_submission(submission_id)
    assert db_state["status"] == "finalized"
    assert db_state["student_name"] == "Corrected Name"
    assert db_state["name_flagged"] is False


# ---- idempotent capture_id (0005_scan_capture_id) --------------------------


def test_scan_same_capture_id_twice_returns_same_submission_and_creates_no_duplicate(seeded_quiz):
    """Reproduces the exact scenario that surfaced this bug: a client retries
    a /scan call whose original request actually succeeded server-side (e.g.
    the response was lost to a client-side timeout). The retry must return
    the same submission, not create a second one."""
    template = load_template()
    page_rgb = _render_and_rasterize(seeded_quiz)
    write_name_on_page(page_rgb, template, "REPEAT STUDENT", dpi=DPI)
    for row_index, qid in enumerate(seeded_quiz["question_order"]):
        shuffled_pos = _correct_shuffled_position(seeded_quiz, qid)
        _mark_bubble_filled(page_rgb, template, row_index, shuffled_pos)
    image_bytes = _page_to_upload_bytes(page_rgb)

    capture_id = f"capture-{uuid.uuid4()}"
    first = client.post(
        "/scan",
        files={"file": ("scan.png", image_bytes, "image/png")},
        params={"capture_id": capture_id},
    )
    second = client.post(
        "/scan",
        files={"file": ("scan.png", image_bytes, "image/png")},
        params={"capture_id": capture_id},
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json() == second.json(), "a replayed capture_id must return an identical body"

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from submissions where capture_id = %s", (capture_id,))
            submission_count = cur.fetchone()[0]
    assert submission_count == 1, "a replayed capture_id must not create a second submission row"

    db_state = _fetch_submission(first.json()["submission_id"])
    assert len(db_state["answers"]) == 4, "answers must not be duplicated either"


def test_scan_without_capture_id_still_creates_a_new_submission_each_time(seeded_quiz):
    """Unchanged default behavior: callers that don't opt into idempotency
    (capture_id omitted) keep getting a fresh submission per call, exactly
    as before this fix existed."""
    template = load_template()
    page_rgb = _render_and_rasterize(seeded_quiz)
    write_name_on_page(page_rgb, template, "NO CAPTURE ID", dpi=DPI)
    for row_index, qid in enumerate(seeded_quiz["question_order"]):
        shuffled_pos = _correct_shuffled_position(seeded_quiz, qid)
        _mark_bubble_filled(page_rgb, template, row_index, shuffled_pos)
    image_bytes = _page_to_upload_bytes(page_rgb)

    first = client.post("/scan", files={"file": ("scan.png", image_bytes, "image/png")})
    second = client.post("/scan", files={"file": ("scan.png", image_bytes, "image/png")})

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["submission_id"] != second.json()["submission_id"]


def test_create_submission_returns_existing_row_on_capture_id_conflict(seeded_quiz):
    """Service-level concurrency-safety check: a submission already exists
    for a given capture_id (as if a concurrent request won the race) -
    create_submission must return that existing row rather than raising a
    unique-violation."""
    capture_id = f"capture-{uuid.uuid4()}"
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into submissions (version_id, status, total_score, capture_id)
                values (%s, 'finalized', 4.0, %s)
                returning id
                """,
                (str(seeded_quiz["version_id"]), capture_id),
            )
            existing_id = cur.fetchone()[0]
        conn.commit()

    fake_result = ScoringResult(
        total_score=0.0,
        status="finalized",
        answers=[
            ScoredAnswer(
                question_no=1,
                question_id=seeded_quiz["question_order"][0],
                detected_option="A",
                confidence=0.99,
                flagged=False,
                correct=True,
                score=1.0,
            )
        ],
    )
    fake_name = NameDetectionResult(text="Should Not Be Written", confidence=99.0, flagged=False)

    with psycopg.connect(DATABASE_URL) as conn:
        created = submissions_service.create_submission(
            conn,
            seeded_quiz["version_id"],
            fake_result,
            fake_name,
            student_id=None,
            capture_id=capture_id,
        )

    assert created.id == existing_id
    assert created.total_score == 4.0  # the pre-existing row's value, not fake_result's

    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from submissions where capture_id = %s", (capture_id,))
            assert cur.fetchone()[0] == 1
            cur.execute("select count(*) from answers where submission_id = %s", (existing_id,))
            assert cur.fetchone()[0] == 0, "no answers should have been inserted for the conflict"


def test_professor_name_correction_requires_owning_professors_token(seeded_quiz):
    body, _ = _scan_with_one_multi_mark(seeded_quiz)
    submission_id = body["submission_id"]

    other_email = f"other-prof-{uuid.uuid4().hex[:8]}@example.com"
    _, other_token = create_auth_user_and_token(other_email)

    response = client.patch(
        f"/submissions/{submission_id}/name",
        json={"student_name": "Someone Else"},
        headers=auth_headers(other_token),
    )

    assert response.status_code == 404
