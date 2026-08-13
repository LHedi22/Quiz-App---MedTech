"""Subtask 2.3: POST /quizzes/{quiz_id}/upload.

Reworked alongside the Phase 7 (Next.js migration) backend auth fix: this
route now requires a real Supabase-authenticated, quiz-owning professor
(see docs/BLOCKERS.md's "Phase 7 (Next.js migration)" entry), so the
fixture here creates a real Supabase Auth user via
`create_auth_user_and_token` (test_quizzes_endpoint.py) instead of a bare
fabricated `users` row that could never authenticate.
"""

import uuid
from pathlib import Path
from unittest.mock import patch

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from app.db import DATABASE_URL
from app.main import app
from app.models.question import QuestionSchema
from app.services.questions import insert_questions
from tests.test_quizzes_endpoint import (
    SUPABASE_URL,
    auth_headers,
    create_auth_user_and_token,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "excel"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _supabase_reachable() -> bool:
    try:
        httpx.get(f"{SUPABASE_URL}/auth/v1/health", timeout=2.0)
        return True
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(
    not _supabase_reachable(),
    reason="local Supabase stack not reachable (run `supabase start` in /backend)",
)

client = TestClient(app)


def run_sql(sql: str) -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)


def question_count(quiz_id) -> int:
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("select count(*) from questions where quiz_id = %s", (str(quiz_id),))
            return cur.fetchone()[0]


@pytest.fixture
def demo_quiz():
    suffix = uuid.uuid4().hex[:8]
    user_id, token = create_auth_user_and_token(f"upload-test-{suffix}@example.com")
    quiz_id = uuid.uuid4()
    run_sql(f"""
        insert into users (id, email) values ('{user_id}', 'upload-test-{suffix}@example.com');
        insert into quizzes (id, owner_id, title)
          values ('{quiz_id}', '{user_id}', 'Upload test quiz');
        """)
    yield {"quiz_id": quiz_id, "token": token}
    # quizzes.owner_id -> users.id is NO ACTION (not cascade) per CLAUDE.md Section 4,
    # so quizzes must be deleted before users; quizzes -> questions is cascade.
    run_sql(f"""
        delete from quizzes where id = '{quiz_id}';
        delete from users where id = '{user_id}';
        delete from auth.users where id = '{user_id}';
        """)


def upload(quiz_id, fixture_name: str, token: str):
    with open(FIXTURES_DIR / fixture_name, "rb") as f:
        return client.post(
            f"/quizzes/{quiz_id}/upload",
            files={"file": (fixture_name, f, XLSX_CONTENT_TYPE)},
            headers=auth_headers(token),
        )


def test_valid_upload_returns_201_and_inserts_correct_rows(demo_quiz):
    quiz_id = demo_quiz["quiz_id"]
    response = upload(quiz_id, "valid.xlsx", demo_quiz["token"])

    assert response.status_code == 201
    assert response.json() == {"quiz_id": str(quiz_id), "questions_inserted": 3}
    assert question_count(quiz_id) == 3


def test_missing_answer_upload_returns_422_with_structured_errors_and_writes_nothing(demo_quiz):
    quiz_id = demo_quiz["quiz_id"]
    response = upload(quiz_id, "missing_answer.xlsx", demo_quiz["token"])

    assert response.status_code == 422
    errors = response.json()["detail"]["errors"]
    assert errors == [
        {
            "row_number": 3,
            "messages": ["correct_option must be exactly one of A/B/C/D, got ''"],
        }
    ]
    assert question_count(quiz_id) == 0


def test_duplicate_options_upload_returns_422_with_structured_errors_and_writes_nothing(demo_quiz):
    quiz_id = demo_quiz["quiz_id"]
    response = upload(quiz_id, "duplicate_options.xlsx", demo_quiz["token"])

    assert response.status_code == 422
    errors = response.json()["detail"]["errors"]
    assert errors == [
        {
            "row_number": 3,
            "messages": ["options must be unique within the row (duplicate option text found)"],
        }
    ]
    assert question_count(quiz_id) == 0


def test_upload_to_nonexistent_quiz_returns_404_and_writes_nothing(demo_quiz):
    # A real, authenticated professor still gets 404 (not a leaked 401/403)
    # for a quiz id that doesn't belong to them.
    fake_quiz_id = uuid.uuid4()
    response = upload(fake_quiz_id, "valid.xlsx", demo_quiz["token"])

    assert response.status_code == 404
    assert question_count(fake_quiz_id) == 0


def test_upload_requires_auth():
    fake_quiz_id = uuid.uuid4()
    with open(FIXTURES_DIR / "valid.xlsx", "rb") as f:
        response = client.post(
            f"/quizzes/{fake_quiz_id}/upload",
            files={"file": ("valid.xlsx", f, XLSX_CONTENT_TYPE)},
        )
    assert response.status_code in (401, 422)


def test_insert_questions_rolls_back_entirely_when_a_later_row_fails(demo_quiz):
    """Proves insert_questions -- the function the upload endpoint relies on
    for its all-or-nothing guarantee -- performs a genuine transactional
    rollback, not just "we never tried to write": the first row's INSERT
    really executes and would have committed on its own, but because the
    second row's INSERT fails, the whole batch (including the first row)
    ends up with zero rows persisted.
    """
    questions = [
        QuestionSchema(
            text="Row one — its own INSERT succeeds but must still be rolled back",
            options=["A", "B", "C", "D"],
            correct_option="A",
            order_index=1,
        ),
        QuestionSchema(
            text="Row two — this is where the simulated failure happens",
            options=["A", "B", "C", "D"],
            correct_option="B",
            order_index=2,
        ),
    ]

    original_execute = psycopg.Cursor.execute
    call_count = {"n": 0}

    def flaky_execute(self, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise psycopg.OperationalError("simulated mid-batch failure")
        return original_execute(self, *args, **kwargs)

    quiz_id = demo_quiz["quiz_id"]
    with psycopg.connect(DATABASE_URL) as conn:
        with patch.object(psycopg.Cursor, "execute", flaky_execute):
            with pytest.raises(psycopg.OperationalError):
                insert_questions(conn, quiz_id, questions)

    assert question_count(quiz_id) == 0
