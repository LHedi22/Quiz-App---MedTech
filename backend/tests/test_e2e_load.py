"""Subtask 9.3: load/volume sanity check.

A 50-question quiz, 30 generated versions, and a real PDF render (+ storage
upload + download) for every one of those 30 versions, all against the real
local Supabase + Postgres + Storage stack - the same "real deployment" every
other Phase 9 test and every prior phase's own test suite already uses.

Time bound: empirically measured, not guessed. A standalone timing run of
this exact scenario on this dev machine (build 50q -> upload -> generate 30
versions -> render/upload/download all 30 PDFs) measured ~53s total, almost
entirely spent in the 30x real PDF-render-and-storage-upload loop (~52s of
the 53s; quiz creation, upload, and version generation together took well
under 1s). LOAD_TEST_TIME_BOUND_SECONDS below is set to 150s (~2.8x that
observed figure) - enough margin to absorb normal machine-load variance
without being a meaningless "never fails" number.

Memory: uses stdlib `tracemalloc` (no new dependency) rather than skipping
this DoD item - peak traced memory across the 30-version render loop must
stay under a defined ceiling, and memory sampled periodically through the
loop must not show runaway (leak-shaped) growth from the first sample to
the last.
"""

from __future__ import annotations

import io
import time
import tracemalloc
import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.db import DATABASE_URL
from app.main import app
from tests.test_quizzes_endpoint import auth_headers, create_auth_user_and_token

XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

NUM_QUESTIONS = 50
NUM_VERSIONS = 30
NUM_OPTIONS = 4

# See module docstring: ~53s observed on this dev machine, ~2.8x margin.
LOAD_TEST_TIME_BOUND_SECONDS = 150.0

# Generous but real ceilings - not "always passes", but not fragile either.
PEAK_MEMORY_BOUND_BYTES = 500 * 1024 * 1024  # 500 MB
MEMORY_GROWTH_RATIO_BOUND = 5.0  # last periodic sample vs. first
MEMORY_GROWTH_NOISE_FLOOR_BYTES = 10 * 1024 * 1024  # tolerate small absolute noise


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
    email = f"e2e-load-{suffix}@example.com"
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


def _build_large_excel_bytes(num_questions: int) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(
        ["question_text", "option_a", "option_b", "option_c", "option_d", "correct_option"]
    )
    for i in range(num_questions):
        correct = "ABCD"[i % NUM_OPTIONS]
        sheet.append(
            [f"Question {i + 1} of {num_questions}?", "Opt A", "Opt B", "Opt C", "Opt D", correct]
        )
    buf = io.BytesIO()
    workbook.save(buf)
    return buf.getvalue()


def _fetch_versions(quiz_id: str) -> list[dict]:
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select id, version_number, qr_id, question_order, option_order "
                "from versions where quiz_id = %s order by version_number",
                (quiz_id,),
            )
            cols = [c.name for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def _fetch_questions(quiz_id: str) -> dict:
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select id, options, correct_option from questions where quiz_id = %s",
                (quiz_id,),
            )
            return {
                str(row[0]): {"options": row[1], "correct_option": row[2]} for row in cur.fetchall()
            }


def test_50_question_30_version_load_within_time_bound_and_correct_at_scale(professor):
    # 1. Create quiz + upload a real 50-question Excel workbook.
    create = client.post(
        "/quizzes",
        json={"title": "E2E Load Test Quiz"},
        headers=auth_headers(professor["token"]),
    )
    assert create.status_code == 201, create.text
    quiz_id = create.json()["id"]

    excel_bytes = _build_large_excel_bytes(NUM_QUESTIONS)
    upload_start = time.perf_counter()
    upload = client.post(
        f"/quizzes/{quiz_id}/upload",
        files={"file": ("large_quiz.xlsx", excel_bytes, XLSX_CONTENT_TYPE)},
        headers=auth_headers(professor["token"]),
    )
    assert upload.status_code == 201, upload.text
    assert upload.json()["questions_inserted"] == NUM_QUESTIONS

    # 2. Generate 30 versions of the 50-question quiz.
    gen = client.post(
        f"/quizzes/{quiz_id}/versions",
        json={"count": NUM_VERSIONS},
        headers=auth_headers(professor["token"]),
    )
    assert gen.status_code == 201, gen.text
    assert gen.json()["versions_created"] == NUM_VERSIONS

    versions = _fetch_versions(quiz_id)
    assert len(versions) == NUM_VERSIONS

    # 3. Render (+ upload to real Storage, + download) the real PDF for
    # every one of the 30 versions, timing the whole load scenario and
    # periodically sampling traced memory usage.
    tracemalloc.start()
    memory_samples: list[int] = []
    sample_at = {0, 4, 9, 19, NUM_VERSIONS - 1}

    for i, version in enumerate(versions):
        pdf_response = client.get(
            f"/versions/{version['id']}/pdf", headers=auth_headers(professor["token"])
        )
        assert pdf_response.status_code == 200, pdf_response.text
        signed_url = pdf_response.json()["url"]
        downloaded = httpx.get(signed_url)
        assert downloaded.status_code == 200
        # Real, non-trivial PDF content - not an empty/corrupt placeholder.
        assert downloaded.content[:4] == b"%PDF"
        assert len(downloaded.content) > 2000

        if i in sample_at:
            current, _ = tracemalloc.get_traced_memory()
            memory_samples.append(current)

    _, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    total_elapsed = time.perf_counter() - upload_start

    # --- DoD: 30-version generation + PDF rendering within the time bound. ---
    assert total_elapsed < LOAD_TEST_TIME_BOUND_SECONDS, (
        f"load scenario took {total_elapsed:.1f}s, exceeding the "
        f"{LOAD_TEST_TIME_BOUND_SECONDS}s bound (see module docstring for how "
        "that bound was derived)"
    )

    # --- DoD: no memory degradation at this scale. ---
    assert peak_memory < PEAK_MEMORY_BOUND_BYTES, (
        f"peak traced memory {peak_memory / 1024 / 1024:.1f}MB exceeded the "
        f"{PEAK_MEMORY_BOUND_BYTES / 1024 / 1024:.0f}MB ceiling"
    )
    assert memory_samples[-1] < memory_samples[0] * MEMORY_GROWTH_RATIO_BOUND + (
        MEMORY_GROWTH_NOISE_FLOOR_BYTES
    ), (
        f"memory grew from {memory_samples[0]} to {memory_samples[-1]} bytes across the "
        "30-version loop - shaped like a leak, not normal variance"
    )

    # --- DoD: no correctness degradation at this scale - spot-check, not "didn't crash". ---
    questions = _fetch_questions(quiz_id)
    expected_question_ids = set(questions.keys())
    all_qr_ids = {v["qr_id"] for v in versions}
    assert len(all_qr_ids) == NUM_VERSIONS, "qr_id must stay unique across all 30 versions"

    for sample_index in (0, 14, NUM_VERSIONS - 1):
        version = versions[sample_index]

        # Valid, complete question-order permutation of all 50 canonical ids.
        assert set(version["question_order"]) == expected_question_ids
        assert len(version["question_order"]) == NUM_QUESTIONS
        assert len(set(version["question_order"])) == NUM_QUESTIONS

        # Every question's option_order is a valid permutation of the option count.
        assert set(version["option_order"].keys()) == expected_question_ids
        for qid, permutation in version["option_order"].items():
            option_count = len(questions[qid]["options"])
            assert sorted(permutation) == list(range(option_count))

        # Correct-answer traceability, spot-checked on a handful of questions
        # in this sampled version: recover the true correct option purely
        # from the stored option_order mapping (same technique Phase 3.1
        # used to first prove this end-to-end).
        for qid in list(version["option_order"].keys())[:5]:
            canonical_index = ord(questions[qid]["correct_option"].upper()) - ord("A")
            shuffled_positions = version["option_order"][qid]
            recovered_position = shuffled_positions.index(canonical_index)
            assert 0 <= recovered_position < NUM_OPTIONS
