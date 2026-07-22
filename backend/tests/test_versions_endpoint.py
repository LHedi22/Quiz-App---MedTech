"""Subtask 3.3: POST /quizzes/{quiz_id}/versions + storage + immutability."""

import uuid
from collections import Counter

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Json

from app.db import DATABASE_URL
from app.main import app


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


def fetch_versions(quiz_id):
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select id, version_number, qr_id, question_order, option_order "
                "from versions where quiz_id = %s order by version_number",
                (str(quiz_id),),
            )
            cols = [c.name for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_questions(quiz_id):
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select id, options, correct_option from questions where quiz_id = %s",
                (str(quiz_id),),
            )
            return {
                str(row[0]): {"options": row[1], "correct_option": row[2]} for row in cur.fetchall()
            }


@pytest.fixture
def quiz_with_questions():
    user_id = uuid.uuid4()
    quiz_id = uuid.uuid4()
    run_sql(f"""
        insert into users (id, email) values ('{user_id}', 'versions-test-{user_id}@example.com');
        insert into quizzes (id, owner_id, title)
          values ('{quiz_id}', '{user_id}', 'Versions test quiz');
        """)
    question_ids = [uuid.uuid4() for _ in range(6)]
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            for i, qid in enumerate(question_ids):
                cur.execute(
                    """
                    insert into questions (id, quiz_id, text, options, correct_option, order_index)
                    values (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(qid),
                        str(quiz_id),
                        f"Question {i}",
                        Json(["A opt", "B opt", "C opt", "D opt"]),
                        "ABCD"[i % 4],
                        i,
                    ),
                )
        conn.commit()
    yield quiz_id
    run_sql(f"""
        delete from quizzes where id = '{quiz_id}';
        delete from users where id = '{user_id}';
        """)


@pytest.fixture
def empty_quiz():
    user_id = uuid.uuid4()
    quiz_id = uuid.uuid4()
    run_sql(f"""
        insert into users (id, email) values ('{user_id}', 'empty-quiz-{user_id}@example.com');
        insert into quizzes (id, owner_id, title)
          values ('{quiz_id}', '{user_id}', 'Empty quiz');
        """)
    yield quiz_id
    run_sql(f"""
        delete from quizzes where id = '{quiz_id}';
        delete from users where id = '{user_id}';
        """)


def test_requesting_5_versions_creates_exactly_5_valid_rows(quiz_with_questions):
    response = client.post(f"/quizzes/{quiz_with_questions}/versions", json={"count": 5})

    assert response.status_code == 201
    assert response.json() == {"quiz_id": str(quiz_with_questions), "versions_created": 5}

    rows = fetch_versions(quiz_with_questions)
    assert len(rows) == 5
    assert sorted(r["version_number"] for r in rows) == [1, 2, 3, 4, 5]

    questions = fetch_questions(quiz_with_questions)
    expected_question_ids = set(questions.keys())
    qr_ids = set()

    for row in rows:
        qr_ids.add(row["qr_id"])

        assert set(row["question_order"]) == expected_question_ids
        assert len(row["question_order"]) == len(set(row["question_order"]))

        assert set(row["option_order"].keys()) == expected_question_ids
        for qid, permutation in row["option_order"].items():
            option_count = len(questions[qid]["options"])
            assert sorted(permutation) == list(range(option_count))

        max_allowed = int(len(questions) * 0.5)
        counts = Counter()
        for qid, question in questions.items():
            canonical_index = ord(question["correct_option"]) - ord("A")
            shuffled_positions = row["option_order"][qid]
            new_index = shuffled_positions.index(canonical_index)
            counts[chr(ord("A") + new_index)] += 1
        assert max(counts.values()) <= max_allowed

    assert len(qr_ids) == 5, "qr_id must be unique per version"


def test_zero_question_quiz_returns_400_and_writes_nothing(empty_quiz):
    response = client.post(f"/quizzes/{empty_quiz}/versions", json={"count": 3})

    assert response.status_code == 400
    assert fetch_versions(empty_quiz) == []


def test_count_less_than_1_returns_400(quiz_with_questions):
    response = client.post(f"/quizzes/{quiz_with_questions}/versions", json={"count": 0})

    assert response.status_code == 400
    assert fetch_versions(quiz_with_questions) == []


def test_nonexistent_quiz_returns_404():
    fake_quiz_id = uuid.uuid4()
    response = client.post(f"/quizzes/{fake_quiz_id}/versions", json={"count": 2})

    assert response.status_code == 404


def test_no_update_endpoint_exists_for_versions(quiz_with_questions):
    """Subtask 3.3: versions must be immutable once created — no code path may
    update question_order/option_order after creation.
    """
    client.post(f"/quizzes/{quiz_with_questions}/versions", json={"count": 1})
    version_id = fetch_versions(quiz_with_questions)[0]["id"]

    for method in ("put", "patch", "delete"):
        response = getattr(client, method)(f"/versions/{version_id}")
        assert response.status_code in (404, 405), (
            f"{method.upper()} /versions/{{id}} should not exist (route not registered), "
            f"got {response.status_code}"
        )
    for method in ("put", "patch"):
        response = getattr(client, method)(f"/quizzes/{quiz_with_questions}/versions/{version_id}")
        assert response.status_code in (404, 405)


def _iter_api_routes(routes):
    """FastAPI >=0.139 wraps included routers in `_IncludedRouter`, which defers
    exposing the real `APIRoute` objects on `app.routes` until app.setup() runs;
    `original_router` gives direct access to the actual mounted routes regardless.
    """
    for route in routes:
        nested = getattr(route, "original_router", None)
        if nested is not None:
            yield from _iter_api_routes(nested.routes)
        elif hasattr(route, "path") and hasattr(route, "methods"):
            yield route


def test_registered_routes_have_no_version_mutation_path():
    """Belt-and-suspenders check straight against the FastAPI route table: no
    route touching `versions` supports PUT/PATCH.
    """
    matching = [r for r in _iter_api_routes(app.routes) if "versions" in r.path]
    assert matching, "expected to find the /quizzes/{quiz_id}/versions route"
    for route in matching:
        assert not (
            {"PUT", "PATCH"} & route.methods
        ), f"found a mutating method on {route.path}: {route.methods}"
