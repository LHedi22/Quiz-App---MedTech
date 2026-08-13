"""Cross-user RLS verification for Phase 1.2.

Exercises the real auth.uid()-scoped path: signs in as two distinct Supabase Auth
users and issues PostgREST requests with their JWTs, rather than asserting on raw
SQL. Requires a local Supabase stack (`supabase start` in /backend); skips cleanly
if one isn't reachable, since this is an integration test against live Postgres +
GoTrue + PostgREST, not a unit test.
"""

import os
import uuid

import httpx
import psycopg
import pytest

SUPABASE_URL = os.environ.get("SUPABASE_URL", "http://127.0.0.1:54341")
ANON_KEY = os.environ.get(
    "SUPABASE_ANON_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9."
    "CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0",
)
SERVICE_ROLE_KEY = os.environ.get(
    "SUPABASE_SERVICE_ROLE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0."
    "EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU",
)
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:54342/postgres"
)
TEST_PASSWORD = "test-password-123!"


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


def run_sql(sql: str) -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)


def create_auth_user(email: str) -> str:
    response = httpx.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers={"apikey": SERVICE_ROLE_KEY, "Authorization": f"Bearer {SERVICE_ROLE_KEY}"},
        json={"email": email, "password": TEST_PASSWORD, "email_confirm": True},
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()["id"]


def sign_in(email: str) -> str:
    response = httpx.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": ANON_KEY},
        json={"email": email, "password": TEST_PASSWORD},
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def rest_get(table: str, access_token: str) -> list[dict]:
    response = httpx.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers={
            "apikey": ANON_KEY,
            "Authorization": f"Bearer {access_token}",
        },
        params={"select": "*"},
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()


class TwoUserFixture:
    def __init__(self):
        self.suffix = uuid.uuid4().hex[:8]
        self.email_a = f"rls-test-a-{self.suffix}@example.com"
        self.email_b = f"rls-test-b-{self.suffix}@example.com"


@pytest.fixture(scope="module")
def two_users():
    fixture = TwoUserFixture()

    user_a_id = create_auth_user(fixture.email_a)
    user_b_id = create_auth_user(fixture.email_b)

    quiz_a_id, quiz_b_id = str(uuid.uuid4()), str(uuid.uuid4())
    question_a_id, question_b_id = str(uuid.uuid4()), str(uuid.uuid4())
    version_a_id, version_b_id = str(uuid.uuid4()), str(uuid.uuid4())
    submission_a_id, submission_b_id = str(uuid.uuid4()), str(uuid.uuid4())
    answer_a_id, answer_b_id = str(uuid.uuid4()), str(uuid.uuid4())

    run_sql(f"""
        insert into users (id, email) values
          ('{user_a_id}', '{fixture.email_a}'),
          ('{user_b_id}', '{fixture.email_b}');

        insert into quizzes (id, owner_id, title) values
          ('{quiz_a_id}', '{user_a_id}', 'User A Quiz'),
          ('{quiz_b_id}', '{user_b_id}', 'User B Quiz');

        insert into questions (id, quiz_id, text, options, correct_option, order_index) values
          ('{question_a_id}', '{quiz_a_id}', 'A question?', '["X", "Y"]', 'A', 1),
          ('{question_b_id}', '{quiz_b_id}', 'B question?', '["X", "Y"]', 'A', 1);

        insert into versions
          (id, quiz_id, version_number, qr_id, question_order, option_order) values
          ('{version_a_id}', '{quiz_a_id}', 1, 'qr-a-{fixture.suffix}',
           '["{question_a_id}"]', '{{"{question_a_id}": [0, 1]}}'),
          ('{version_b_id}', '{quiz_b_id}', 1, 'qr-b-{fixture.suffix}',
           '["{question_b_id}"]', '{{"{question_b_id}": [0, 1]}}');

        insert into submissions (id, version_id, status) values
          ('{submission_a_id}', '{version_a_id}', 'pending'),
          ('{submission_b_id}', '{version_b_id}', 'pending');

        insert into answers (id, submission_id, question_no, confidence) values
          ('{answer_a_id}', '{submission_a_id}', 1, 0.9),
          ('{answer_b_id}', '{submission_b_id}', 1, 0.9);
    """)

    token_a = sign_in(fixture.email_a)
    token_b = sign_in(fixture.email_b)

    yield {
        "token_a": token_a,
        "token_b": token_b,
        "user_a_id": user_a_id,
        "user_b_id": user_b_id,
        "quiz_a_id": quiz_a_id,
        "quiz_b_id": quiz_b_id,
        "question_a_id": question_a_id,
        "question_b_id": question_b_id,
        "version_a_id": version_a_id,
        "version_b_id": version_b_id,
        "submission_a_id": submission_a_id,
        "submission_b_id": submission_b_id,
        "answer_a_id": answer_a_id,
        "answer_b_id": answer_b_id,
    }

    run_sql(f"""
        delete from submissions where id in ('{submission_a_id}', '{submission_b_id}');
        delete from quizzes where id in ('{quiz_a_id}', '{quiz_b_id}');
        delete from users where id in ('{user_a_id}', '{user_b_id}');
        delete from auth.users where id in ('{user_a_id}', '{user_b_id}');
    """)


@pytest.mark.parametrize("table", ["quizzes", "questions", "versions", "submissions", "answers"])
def test_user_a_sees_zero_rows_of_user_b_data(two_users, table):
    rows = rest_get(table, two_users["token_a"])
    b_id_key = {
        "quizzes": "quiz_b_id",
        "questions": "question_b_id",
        "versions": "version_b_id",
        "submissions": "submission_b_id",
        "answers": "answer_b_id",
    }[table]
    b_id = two_users[b_id_key]
    assert all(
        row["id"] != b_id for row in rows
    ), f"user A saw user B's {table} row {b_id} — RLS policy is leaking cross-user data"


def test_user_a_cannot_see_user_b_profile(two_users):
    rows = rest_get("users", two_users["token_a"])
    assert all(row["id"] != two_users["user_b_id"] for row in rows)


@pytest.mark.parametrize(
    "table,id_key",
    [
        ("quizzes", "quiz_a_id"),
        ("questions", "question_a_id"),
        ("versions", "version_a_id"),
        ("submissions", "submission_a_id"),
        ("answers", "answer_a_id"),
    ],
)
def test_user_a_sees_their_own_data(two_users, table, id_key):
    rows = rest_get(table, two_users["token_a"])
    own_id = two_users[id_key]
    assert any(
        row["id"] == own_id for row in rows
    ), f"user A could not see their own {table} row {own_id} — RLS policy is too restrictive"


def test_user_a_sees_their_own_profile(two_users):
    rows = rest_get("users", two_users["token_a"])
    assert any(row["id"] == two_users["user_a_id"] for row in rows)
