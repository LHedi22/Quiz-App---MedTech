"""Subtask 10.1: Phase-9-style E2E smoke test against a *deployed* backend.

Same scenario and same correctness bar as
`backend/tests/test_e2e_happy_path.py` (Excel upload -> a generated,
independently-shuffled version -> real PDF download -> a synthetic scan
filled with the mathematically correct answers -> a finalized submission
with the exact expected score) but driven entirely over real HTTP against
an arbitrary `BACKEND_URL` (a Cloud Run service URL in production;
`http://127.0.0.1:8081` when smoke-testing the same Docker image locally,
as this repo's own pre-deployment verification did - see
docs/verify_docker_health.md) instead of FastAPI's in-process `TestClient`.

Whoever runs this already holds `SUPABASE_SERVICE_ROLE_KEY` - the same
top-tier credential the Cloud Run deploy itself requires (it bypasses RLS
entirely) - so there is no meaningful extra exposure in also requiring
`DATABASE_URL` here: without it, this script can only prove the pipeline
didn't error, which is a materially weaker bar than Phase 9's "mathematically
correct scores" and is intentionally rejected rather than silently accepted.

Usage:
  BACKEND_URL=https://exam-scanner-backend-xxxx.a.run.app \
  SUPABASE_URL=https://xxxx.supabase.co \
  SUPABASE_ANON_KEY=... \
  SUPABASE_SERVICE_ROLE_KEY=... \
  DATABASE_URL=postgresql://... \
    python scripts/e2e_smoke_test.py
"""

from __future__ import annotations

import io
import os
import sys
import uuid
from pathlib import Path

import cv2
import httpx
import psycopg
from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.geometry import bubble_center_pt, pdf_point_to_pixel  # noqa: E402
from app.services.pdf_gen import load_template  # noqa: E402
from tests.omr_test_utils import render_page_rgb  # noqa: E402

DPI = 200
NUM_QUESTIONS = 3
CORRECT_OPTIONS = ["B", "C", "B"]
TEST_PASSWORD = "smoke-test-password-123!"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _env(name: str, required: bool = True) -> str | None:
    value = os.environ.get(name)
    if required and not value:
        print(f"error: {name} must be set", file=sys.stderr)
        sys.exit(1)
    return value


def create_auth_user_and_token(
    supabase_url: str, anon_key: str, service_role_key: str, email: str
) -> str:
    response = httpx.post(
        f"{supabase_url}/auth/v1/admin/users",
        headers={"apikey": service_role_key, "Authorization": f"Bearer {service_role_key}"},
        json={"email": email, "password": TEST_PASSWORD, "email_confirm": True},
        timeout=15.0,
    )
    response.raise_for_status()

    response = httpx.post(
        f"{supabase_url}/auth/v1/token?grant_type=password",
        headers={"apikey": anon_key},
        json={"email": email, "password": TEST_PASSWORD},
        timeout=15.0,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _build_excel_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(
        ["question_text", "option_a", "option_b", "option_c", "option_d", "correct_option"]
    )
    for i in range(NUM_QUESTIONS):
        sheet.append(
            [
                f"Smoke test question {i + 1}?",
                "Opt A",
                "Opt B",
                "Opt C",
                "Opt D",
                CORRECT_OPTIONS[i],
            ]
        )
    buf = io.BytesIO()
    workbook.save(buf)
    return buf.getvalue()


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


def _fetch_version_mapping(database_url: str, version_id: str) -> dict:
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select question_order, option_order from versions where id = %s", (version_id,)
            )
            question_order, option_order = cur.fetchone()
            cur.execute(
                "select id, order_index, correct_option from questions where id = any(%s)",
                (question_order,),
            )
            questions = {
                str(row[0]): {"order_index": row[1], "correct_option": row[2]}
                for row in cur.fetchall()
            }
    return {"question_order": question_order, "option_order": option_order, "questions": questions}


def main() -> None:
    backend_url = _env("BACKEND_URL").rstrip("/")
    supabase_url = _env("SUPABASE_URL").rstrip("/")
    anon_key = _env("SUPABASE_ANON_KEY")
    service_role_key = _env("SUPABASE_SERVICE_ROLE_KEY")
    database_url = _env("DATABASE_URL")

    print(f"1. GET {backend_url}/health ...")
    health = httpx.get(f"{backend_url}/health", timeout=15.0)
    assert health.status_code == 200, health.text
    print(f"   OK: {health.json()}")

    print("2. Creating a disposable professor account + quiz ...")
    email = f"smoke-{uuid.uuid4().hex[:8]}@example.com"
    token = create_auth_user_and_token(supabase_url, anon_key, service_role_key, email)
    headers = {"Authorization": f"Bearer {token}"}

    create = httpx.post(
        f"{backend_url}/quizzes",
        json={"title": "Deploy Smoke Test Quiz"},
        headers=headers,
        timeout=15.0,
    )
    assert create.status_code == 201, create.text
    quiz_id = create.json()["id"]

    print("3. Uploading Excel + generating a version ...")
    upload = httpx.post(
        f"{backend_url}/quizzes/{quiz_id}/upload",
        files={"file": ("smoke.xlsx", _build_excel_bytes(), XLSX_CONTENT_TYPE)},
        timeout=15.0,
    )
    assert upload.status_code == 201, upload.text
    assert upload.json()["questions_inserted"] == NUM_QUESTIONS

    gen = httpx.post(
        f"{backend_url}/quizzes/{quiz_id}/versions",
        json={"count": 1},
        headers=headers,
        timeout=15.0,
    )
    assert gen.status_code == 201, gen.text

    versions = httpx.get(f"{backend_url}/quizzes/{quiz_id}/versions", headers=headers, timeout=15.0)
    version_id = versions.json()[0]["id"]

    print("4. Downloading the real PDF and marking the mathematically correct bubbles ...")
    pdf_meta = httpx.get(f"{backend_url}/versions/{version_id}/pdf", timeout=30.0)
    assert pdf_meta.status_code == 200, pdf_meta.text
    pdf_bytes = httpx.get(pdf_meta.json()["url"], timeout=30.0).content

    mapping = _fetch_version_mapping(database_url, version_id)
    template = load_template()
    page_rgb = render_page_rgb(pdf_bytes, dpi=DPI)

    for row_index, qid in enumerate(mapping["question_order"]):
        question = mapping["questions"][str(qid)]
        canonical_index = ord(question["correct_option"].upper()) - ord("A")
        permutation = mapping["option_order"][str(qid)]
        shuffled_pos = permutation.index(canonical_index)
        _mark_bubble(page_rgb, template, row_index, shuffled_pos)

    print("5. POST /scan ...")
    scan = httpx.post(
        f"{backend_url}/scan",
        files={"file": ("scan.png", _page_to_upload_bytes(page_rgb), "image/png")},
        timeout=30.0,
    )
    assert scan.status_code == 201, scan.text
    body = scan.json()
    assert body["status"] == "finalized", body
    assert body["total_score"] == float(NUM_QUESTIONS), body
    assert body["flagged_question_numbers"] == [], body

    print(
        f"\nSMOKE TEST PASSED against {backend_url}: health, auth, upload, version "
        f"generation, real PDF download+render, and /scan all round-tripped "
        f"successfully, finalizing with the exact expected score "
        f"{body['total_score']}/{NUM_QUESTIONS}."
    )


if __name__ == "__main__":
    main()
