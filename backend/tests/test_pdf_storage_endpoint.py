"""Subtask 4.3: GET /versions/{version_id}/pdf — storage + idempotent download.

Reworked alongside the Phase 7 (Next.js migration) backend auth fix: this
route now requires a real Supabase-authenticated, quiz-owning professor
(see docs/BLOCKERS.md's "Phase 7 (Next.js migration)" entry), so the
fixture here creates a real Supabase Auth user via
`create_auth_user_and_token` (test_quizzes_endpoint.py) instead of a bare
fabricated `users` row that could never authenticate.
"""

import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Json

import app.routers.versions as versions_router
from app.db import DATABASE_URL
from app.main import app
from app.services import storage
from app.services.pdf_gen import render_version_pdf
from app.services.versions import get_version_for_render
from tests.test_quizzes_endpoint import (
    SUPABASE_URL,
    auth_headers,
    create_auth_user_and_token,
)


def _supabase_reachable() -> bool:
    try:
        httpx.get(f"{SUPABASE_URL}/auth/v1/health", timeout=2.0)
        return True
    except httpx.HTTPError:
        return False


def _storage_reachable() -> bool:
    try:
        resp = httpx.get(
            f"{storage.SUPABASE_URL}/storage/v1/bucket",
            headers=storage._headers(),
            timeout=2,
        )
        return resp.status_code < 500
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(
    not (_supabase_reachable() and _storage_reachable()),
    reason="local Supabase stack/Storage not reachable (run `supabase start` in /backend)",
)

client = TestClient(app)


def run_sql(sql: str) -> None:
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)


@pytest.fixture
def version_with_questions():
    suffix = uuid.uuid4().hex[:8]
    user_id, token = create_auth_user_and_token(f"pdf-endpoint-{suffix}@example.com")
    quiz_id = uuid.uuid4()
    run_sql(f"""
        insert into users (id, email) values ('{user_id}', 'pdf-endpoint-{suffix}@example.com');
        insert into quizzes (id, owner_id, title)
          values ('{quiz_id}', '{user_id}', 'PDF Storage Test Quiz');
        """)
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            for i in range(5):
                cur.execute(
                    """
                    insert into questions (id, quiz_id, text, options, correct_option, order_index)
                    values (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid.uuid4()),
                        str(quiz_id),
                        f"Question {i}",
                        Json(["A opt", "B opt", "C opt", "D opt"]),
                        "ABCD"[i % 4],
                        i,
                    ),
                )
        conn.commit()

    response = client.post(
        f"/quizzes/{quiz_id}/versions", json={"count": 1}, headers=auth_headers(token)
    )
    assert response.status_code == 201
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("select id from versions where quiz_id = %s", (str(quiz_id),))
            version_id = cur.fetchone()[0]

    yield quiz_id, version_id, token

    run_sql(f"""
        delete from quizzes where id = '{quiz_id}';
        delete from users where id = '{user_id}';
        delete from auth.users where id = '{user_id}';
        """)


def test_pdf_is_uploaded_and_downloadable_with_matching_content(version_with_questions):
    quiz_id, version_id, token = version_with_questions

    response = client.get(f"/versions/{version_id}/pdf", headers=auth_headers(token))
    assert response.status_code == 200
    signed_url = response.json()["url"]

    downloaded = httpx.get(signed_url)
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] in ("application/pdf", "application/octet-stream")

    with psycopg.connect(DATABASE_URL) as conn:
        quiz_title, version, questions_by_id = get_version_for_render(conn, version_id)
    expected_pdf = render_version_pdf(quiz_title, version, questions_by_id)

    assert downloaded.content == expected_pdf

    path = storage.object_path(quiz_id, version_id)
    assert storage.download_pdf(path) == expected_pdf


def test_repeated_downloads_do_not_regenerate_or_duplicate_the_file(
    version_with_questions, monkeypatch
):
    quiz_id, version_id, token = version_with_questions

    render_calls = []
    original_render = versions_router.render_version_pdf

    def counting_render(*args, **kwargs):
        render_calls.append(1)
        return original_render(*args, **kwargs)

    upload_calls = []
    original_upload = storage.upload_pdf

    def counting_upload(*args, **kwargs):
        upload_calls.append(1)
        return original_upload(*args, **kwargs)

    monkeypatch.setattr(versions_router, "render_version_pdf", counting_render)
    monkeypatch.setattr(storage, "upload_pdf", counting_upload)

    first = client.get(f"/versions/{version_id}/pdf", headers=auth_headers(token))
    second = client.get(f"/versions/{version_id}/pdf", headers=auth_headers(token))
    third = client.get(f"/versions/{version_id}/pdf", headers=auth_headers(token))

    assert first.status_code == second.status_code == third.status_code == 200
    assert len(render_calls) == 1, "PDF must only be generated once, not on every download"
    assert len(upload_calls) == 1, "PDF must only be uploaded once, not on every download"

    path = storage.object_path(quiz_id, version_id)
    first_bytes = httpx.get(first.json()["url"]).content
    third_bytes = httpx.get(third.json()["url"]).content
    assert first_bytes == third_bytes == storage.download_pdf(path)


def test_nonexistent_version_returns_404(version_with_questions):
    # A real, authenticated professor still gets 404 for a version id that
    # doesn't exist (or doesn't belong to them) - not a leaked 401/403.
    _, _, token = version_with_questions
    response = client.get(f"/versions/{uuid.uuid4()}/pdf", headers=auth_headers(token))
    assert response.status_code == 404


def test_download_requires_auth():
    response = client.get(f"/versions/{uuid.uuid4()}/pdf")
    assert response.status_code in (401, 422)
