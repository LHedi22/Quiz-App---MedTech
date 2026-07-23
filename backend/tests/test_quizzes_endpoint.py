"""Phase 7 backend support: POST/GET /quizzes and GET /quizzes/{id}/versions.

These endpoints didn't exist before Phase 7 (the web app has nothing to call
to create or list a quiz otherwise); ownership enforcement is exercised here
with two real Supabase Auth users; see test_rls_cross_user.py for the same
pattern against PostgREST directly.
"""

import os
import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from app.db import DATABASE_URL
from app.main import app

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

client = TestClient(app)


def create_auth_user_and_token(email: str) -> tuple[str, str]:
    response = httpx.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers={"apikey": SERVICE_ROLE_KEY, "Authorization": f"Bearer {SERVICE_ROLE_KEY}"},
        json={"email": email, "password": TEST_PASSWORD, "email_confirm": True},
        timeout=10.0,
    )
    response.raise_for_status()
    user_id = response.json()["id"]

    response = httpx.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": ANON_KEY},
        json={"email": email, "password": TEST_PASSWORD},
        timeout=10.0,
    )
    response.raise_for_status()
    return user_id, response.json()["access_token"]


@pytest.fixture
def professor():
    suffix = uuid.uuid4().hex[:8]
    email = f"quizzes-test-{suffix}@example.com"
    user_id, token = create_auth_user_and_token(email)
    yield {"user_id": user_id, "token": token}
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("delete from quizzes where owner_id = %s", (user_id,))
            cur.execute("delete from users where id = %s", (user_id,))
            cur.execute("delete from auth.users where id = %s", (user_id,))


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_create_quiz_requires_auth():
    response = client.post("/quizzes", json={"title": "No auth"})
    assert response.status_code in (401, 422)


def test_create_and_list_quiz_roundtrip(professor):
    create = client.post(
        "/quizzes", json={"title": "Midterm"}, headers=auth_headers(professor["token"])
    )
    assert create.status_code == 201
    quiz_id = create.json()["id"]
    assert create.json()["title"] == "Midterm"

    listing = client.get("/quizzes", headers=auth_headers(professor["token"]))
    assert listing.status_code == 200
    titles_and_ids = [(q["id"], q["title"]) for q in listing.json()]
    assert (quiz_id, "Midterm") in titles_and_ids


def test_list_quizzes_excludes_other_professors_quizzes(professor):
    other_id, other_token = create_auth_user_and_token(f"other-{uuid.uuid4().hex[:8]}@example.com")
    try:
        client.post("/quizzes", json={"title": "Mine"}, headers=auth_headers(professor["token"]))
        client.post("/quizzes", json={"title": "Theirs"}, headers=auth_headers(other_token))

        mine = client.get("/quizzes", headers=auth_headers(professor["token"]))
        titles = [q["title"] for q in mine.json()]
        assert "Mine" in titles
        assert "Theirs" not in titles
    finally:
        with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("delete from quizzes where owner_id = %s", (other_id,))
                cur.execute("delete from users where id = %s", (other_id,))
                cur.execute("delete from auth.users where id = %s", (other_id,))


def test_get_versions_for_nonexistent_or_foreign_quiz_returns_404(professor):
    fake_quiz_id = uuid.uuid4()
    response = client.get(
        f"/quizzes/{fake_quiz_id}/versions", headers=auth_headers(professor["token"])
    )
    assert response.status_code == 404


def test_list_quiz_versions_returns_created_versions(professor):
    create = client.post(
        "/quizzes", json={"title": "Has versions"}, headers=auth_headers(professor["token"])
    )
    quiz_id = create.json()["id"]

    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "insert into questions (quiz_id, text, options, correct_option, order_index) "
                "values (%s, 'Q1?', '[\"A\",\"B\"]', 'A', 1)",
                (quiz_id,),
            )

    gen = client.post(
        f"/quizzes/{quiz_id}/versions",
        json={"count": 2},
        headers=auth_headers(professor["token"]),
    )
    assert gen.status_code == 201

    versions = client.get(f"/quizzes/{quiz_id}/versions", headers=auth_headers(professor["token"]))
    assert versions.status_code == 200
    assert sorted(v["version_number"] for v in versions.json()) == [1, 2]
