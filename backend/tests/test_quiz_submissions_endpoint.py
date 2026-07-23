"""Phase 7 backend support: GET /quizzes/{id}/submissions (per-quiz, mixed
statuses, for the results dashboard) and GET /submissions/{id} (single
submission detail with answers, for the flagged-answer review screen -
needed before a professor has anything to correct).
"""

import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Json

from app.db import DATABASE_URL
from app.main import app
from tests.test_quizzes_endpoint import (
    _supabase_reachable,
    auth_headers,
    create_auth_user_and_token,
)

pytestmark = pytest.mark.skipif(
    not _supabase_reachable(),
    reason="local Supabase stack not reachable (run `supabase start` in /backend)",
)

client = TestClient(app)


def run_sql(sql: str, params: tuple = ()) -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)


@pytest.fixture
def seeded_quiz_with_mixed_submissions():
    suffix = uuid.uuid4().hex[:8]
    user_id, token = create_auth_user_and_token(f"dash-{suffix}@example.com")
    quiz_id = uuid.uuid4()
    question_id = uuid.uuid4()
    version_id = uuid.uuid4()
    finalized_id = uuid.uuid4()
    needs_review_id = uuid.uuid4()
    pending_id = uuid.uuid4()

    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            # public.users is populated lazily by ensure_user_row() on a
            # professor's first authenticated backend call; insert it here
            # directly since this fixture writes quizzes before making any.
            cur.execute(
                "insert into users (id, email) values (%s, %s)",
                (user_id, f"dash-{suffix}@example.com"),
            )
            cur.execute(
                "insert into quizzes (id, owner_id, title) values (%s, %s, %s)",
                (quiz_id, user_id, "Dashboard quiz"),
            )
            cur.execute(
                "insert into questions (id, quiz_id, text, options, correct_option, order_index) "
                "values (%s, %s, 'Q1?', %s, 'A', 1)",
                (question_id, quiz_id, Json(["A", "B"])),
            )
            cur.execute(
                "insert into versions "
                "(id, quiz_id, version_number, qr_id, question_order, option_order) "
                "values (%s, %s, 1, %s, %s, %s)",
                (
                    version_id,
                    quiz_id,
                    f"qr-{suffix}",
                    Json([str(question_id)]),
                    Json({str(question_id): [0, 1]}),
                ),
            )
            cur.execute(
                "insert into submissions (id, version_id, status, total_score) "
                "values (%s, %s, 'finalized', 1.0)",
                (finalized_id, version_id),
            )
            cur.execute(
                "insert into submissions (id, version_id, status) values (%s, %s, 'needs_review')",
                (needs_review_id, version_id),
            )
            cur.execute(
                "insert into submissions (id, version_id, status) values (%s, %s, 'pending')",
                (pending_id, version_id),
            )
            cur.execute(
                "insert into answers "
                "(submission_id, question_no, detected_option, confidence, flagged) "
                "values (%s, 1, null, 0.4, true)",
                (needs_review_id,),
            )

    yield {
        "token": token,
        "quiz_id": str(quiz_id),
        "finalized_id": str(finalized_id),
        "needs_review_id": str(needs_review_id),
        "pending_id": str(pending_id),
    }

    # submissions/answers aren't cascade-deleted by quizzes/versions (per
    # CLAUDE.md's schema, only questions/versions cascade from quizzes), so
    # they must be cleaned up before the quiz itself.
    run_sql(
        "delete from answers where submission_id in (%s, %s, %s)",
        (finalized_id, needs_review_id, pending_id),
    )
    run_sql(
        "delete from submissions where id in (%s, %s, %s)",
        (finalized_id, needs_review_id, pending_id),
    )
    run_sql("delete from quizzes where id = %s", (quiz_id,))
    run_sql("delete from users where id = %s", (user_id,))
    run_sql("delete from auth.users where id = %s", (user_id,))


def test_quiz_submissions_returns_all_statuses_by_default(seeded_quiz_with_mixed_submissions):
    fixture = seeded_quiz_with_mixed_submissions
    response = client.get(
        f"/quizzes/{fixture['quiz_id']}/submissions", headers=auth_headers(fixture["token"])
    )
    assert response.status_code == 200
    by_id = {s["id"]: s for s in response.json()}
    assert set(by_id) == {
        fixture["finalized_id"],
        fixture["needs_review_id"],
        fixture["pending_id"],
    }
    assert by_id[fixture["finalized_id"]]["status"] == "finalized"
    assert by_id[fixture["finalized_id"]]["total_score"] == 1.0
    assert by_id[fixture["needs_review_id"]]["status"] == "needs_review"
    assert by_id[fixture["pending_id"]]["status"] == "pending"


def test_quiz_submissions_filters_by_status(seeded_quiz_with_mixed_submissions):
    fixture = seeded_quiz_with_mixed_submissions
    response = client.get(
        f"/quizzes/{fixture['quiz_id']}/submissions",
        params={"status": "needs_review"},
        headers=auth_headers(fixture["token"]),
    )
    assert response.status_code == 200
    ids = [s["id"] for s in response.json()]
    assert ids == [fixture["needs_review_id"]]


def test_quiz_submissions_requires_ownership(seeded_quiz_with_mixed_submissions):
    fixture = seeded_quiz_with_mixed_submissions
    other_id, other_token = create_auth_user_and_token(f"other-{uuid.uuid4().hex[:8]}@example.com")
    try:
        response = client.get(
            f"/quizzes/{fixture['quiz_id']}/submissions", headers=auth_headers(other_token)
        )
        assert response.status_code == 404
    finally:
        run_sql("delete from users where id = %s", (other_id,))
        run_sql("delete from auth.users where id = %s", (other_id,))


def test_get_submission_detail_includes_flagged_answers(seeded_quiz_with_mixed_submissions):
    fixture = seeded_quiz_with_mixed_submissions
    response = client.get(f"/submissions/{fixture['needs_review_id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_review"
    assert len(body["answers"]) == 1
    assert body["answers"][0]["flagged"] is True
    assert body["answers"][0]["question_no"] == 1


def test_get_submission_detail_404_for_nonexistent():
    response = client.get(f"/submissions/{uuid.uuid4()}")
    assert response.status_code == 404
