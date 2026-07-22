import uuid
from pathlib import Path
from unittest.mock import patch

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.db import DATABASE_URL
from app.main import app
from app.models.question import QuestionSchema
from app.services.questions import insert_questions

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "excel"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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
    user_id = uuid.uuid4()
    quiz_id = uuid.uuid4()
    run_sql(f"""
        insert into users (id, email) values ('{user_id}', 'upload-test-{user_id}@example.com');
        insert into quizzes (id, owner_id, title)
          values ('{quiz_id}', '{user_id}', 'Upload test quiz');
        """)
    yield quiz_id
    # quizzes.owner_id -> users.id is NO ACTION (not cascade) per CLAUDE.md Section 4,
    # so quizzes must be deleted before users; quizzes -> questions is cascade.
    run_sql(f"""
        delete from quizzes where id = '{quiz_id}';
        delete from users where id = '{user_id}';
        """)


def upload(quiz_id, fixture_name: str):
    with open(FIXTURES_DIR / fixture_name, "rb") as f:
        return client.post(
            f"/quizzes/{quiz_id}/upload",
            files={"file": (fixture_name, f, XLSX_CONTENT_TYPE)},
        )


def test_valid_upload_returns_201_and_inserts_correct_rows(demo_quiz):
    response = upload(demo_quiz, "valid.xlsx")

    assert response.status_code == 201
    assert response.json() == {"quiz_id": str(demo_quiz), "questions_inserted": 3}
    assert question_count(demo_quiz) == 3


def test_missing_answer_upload_returns_422_with_structured_errors_and_writes_nothing(demo_quiz):
    response = upload(demo_quiz, "missing_answer.xlsx")

    assert response.status_code == 422
    errors = response.json()["detail"]["errors"]
    assert errors == [
        {
            "row_number": 3,
            "messages": ["correct_option must be exactly one of A/B/C/D, got ''"],
        }
    ]
    assert question_count(demo_quiz) == 0


def test_duplicate_options_upload_returns_422_with_structured_errors_and_writes_nothing(demo_quiz):
    response = upload(demo_quiz, "duplicate_options.xlsx")

    assert response.status_code == 422
    errors = response.json()["detail"]["errors"]
    assert errors == [
        {
            "row_number": 3,
            "messages": ["options must be unique within the row (duplicate option text found)"],
        }
    ]
    assert question_count(demo_quiz) == 0


def test_upload_to_nonexistent_quiz_returns_404_and_writes_nothing():
    fake_quiz_id = uuid.uuid4()
    response = upload(fake_quiz_id, "valid.xlsx")

    assert response.status_code == 404
    assert question_count(fake_quiz_id) == 0


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

    with psycopg.connect(DATABASE_URL) as conn:
        with patch.object(psycopg.Cursor, "execute", flaky_execute):
            with pytest.raises(psycopg.OperationalError):
                insert_questions(conn, demo_quiz, questions)

    assert question_count(demo_quiz) == 0
