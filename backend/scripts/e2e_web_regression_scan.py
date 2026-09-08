"""Subtask 7b.3/7b.4: seeds a quiz+version(s) and scans them for the Next.js
web-migration regression tests (web/e2e/*.spec.ts).

The web app has no scan-initiating UI at all (scanning is mobile-only per
CLAUDE.md's phase split) - so "driven through the Next.js app" for these
subtasks can only ever apply to the web-facing steps (login, quiz creation,
Excel upload, version generation, PDF download, results dashboard, review
screen). This script performs the one step that has no web equivalent -
downloading the real generated PDF and POSTing a marked scan to /scan,
exactly like backend/tests/test_e2e_happy_path.py and
scripts/e2e_smoke_test.py already do against the real local stack - and
prints machine-readable JSON so a Playwright test can pick up from here and
drive every remaining, genuinely web-facing step through the actual UI.

Usage:
  python scripts/e2e_web_regression_scan.py <command> [args]

Commands:
  seed-quiz <title>
      Creates a professor + quiz + 1 version, uploads valid.xlsx (3
      questions). Prints {"email", "password", "quiz_id", "version_id"}.

  scan <version_id> <mode> <token> [student_id]
      mode is "correct", "wrong:<0-based row index>", or
      "ambiguous:<0-based row index>". <token> is the owning professor's
      access token from seed-quiz - both GET /versions/{id}/pdf and
      POST /scan require it (POST /scan is web-only now, see
      docs/BLOCKERS.md "Web-app audit A2"). Downloads and renders that
      version's real PDF, marks bubbles accordingly, POSTs to /scan.
      Prints {"submission_id", "status", "total_score",
      "flagged_question_numbers", "correct_option_for_flagged_row"}.

  scan-url <version_id> <pdf_url> <mode> <token> [student_id]
      Same as `scan`, but downloads from an already-obtained signed PDF URL
      (e.g. one read out of the Next.js UI's real download link) instead of
      calling GET /versions/{id}/pdf itself - used by the Subtask 7b.4 full
      happy-path test, which drives every web-facing step through the
      actual UI. Prints the same shape as `scan`.

  token <email> <password>
      Mints an access token for an existing account (e.g. one created via
      the real signup UI) so a Playwright test can authenticate the /scan
      step. Prints {"token"}.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

import cv2
import httpx
import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import DATABASE_URL  # noqa: E402
from app.services.geometry import (  # noqa: E402
    bubble_center_pt,
    pdf_point_to_pixel,
    qr_box_pixel_rect,
)
from app.services.pdf_gen import load_template  # noqa: E402
from tests.omr_test_utils import render_page_rgb, write_name_on_page  # noqa: E402

# Same env-var-overridable local-dev defaults as tests/test_quizzes_endpoint.py
# and scripts/e2e_smoke_test.py - not a real secret, Supabase's own published
# demo key for `supabase start`'s local stack.
BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")
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
TEST_PASSWORD = "web-regression-password-123!"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "excel"
DPI = 200


def create_auth_user_and_token(email: str) -> str:
    response = httpx.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers={"apikey": SERVICE_ROLE_KEY, "Authorization": f"Bearer {SERVICE_ROLE_KEY}"},
        json={"email": email, "password": TEST_PASSWORD, "email_confirm": True},
        timeout=15.0,
    )
    response.raise_for_status()

    response = httpx.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": ANON_KEY},
        json={"email": email, "password": TEST_PASSWORD},
        timeout=15.0,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def print_token(email: str, password: str) -> None:
    response = httpx.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": ANON_KEY},
        json={"email": email, "password": password},
        timeout=15.0,
    )
    response.raise_for_status()
    print(json.dumps({"token": response.json()["access_token"]}))


def seed_quiz(title: str) -> None:
    email = f"web-regression-{uuid.uuid4().hex[:8]}@example.com"
    token = create_auth_user_and_token(email)
    headers = {"Authorization": f"Bearer {token}"}

    create = httpx.post(f"{BACKEND_URL}/quizzes", json={"title": title}, headers=headers)
    create.raise_for_status()
    quiz_id = create.json()["id"]

    with open(FIXTURES_DIR / "valid.xlsx", "rb") as f:
        upload = httpx.post(
            f"{BACKEND_URL}/quizzes/{quiz_id}/upload",
            files={"file": ("valid.xlsx", f, XLSX_CONTENT_TYPE)},
            headers=headers,
        )
    upload.raise_for_status()

    gen = httpx.post(
        f"{BACKEND_URL}/quizzes/{quiz_id}/versions", json={"count": 1}, headers=headers
    )
    gen.raise_for_status()

    versions = httpx.get(f"{BACKEND_URL}/quizzes/{quiz_id}/versions", headers=headers)
    versions.raise_for_status()
    version_id = versions.json()[0]["id"]

    print(
        json.dumps(
            {
                "email": email,
                "password": TEST_PASSWORD,
                "token": token,
                "quiz_id": quiz_id,
                "version_id": version_id,
            }
        )
    )


def _fetch_version_mapping(version_id: str) -> dict:
    with psycopg.connect(DATABASE_URL) as conn:
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


def _mark_filled(image, template: dict, row_index: int, option_index: int) -> None:
    x_pt, y_pt = bubble_center_pt(template, row_index, option_index)
    px, py = pdf_point_to_pixel(x_pt, y_pt, template["page_height_pt"], DPI)
    radius_px = int(round(template["bubble_radius_pt"] * DPI / 72.0 * 0.8))
    cv2.circle(image, (int(round(px)), int(round(py))), radius_px, (0, 0, 0), thickness=-1)


def _mark_ambiguous(image, template: dict, row_index: int, option_index: int) -> None:
    # Calibrated in tests/test_e2e_unhappy_path.py: 50% area fraction lands
    # reliably below CONFIDENCE_THRESHOLD on the real trained classifier.
    x_pt, y_pt = bubble_center_pt(template, row_index, option_index)
    px, py = pdf_point_to_pixel(x_pt, y_pt, template["page_height_pt"], DPI)
    full_radius_px = template["bubble_radius_pt"] * DPI / 72.0
    fill_radius_px = int(round(full_radius_px * (0.50**0.5)))
    cv2.circle(image, (int(round(px)), int(round(py))), fill_radius_px, (0, 0, 0), thickness=-1)


def _page_to_upload_bytes(page_rgb) -> bytes:
    bgr = cv2.cvtColor(page_rgb, cv2.COLOR_RGB2BGR)
    ok, encoded = cv2.imencode(".png", bgr)
    assert ok
    return encoded.tobytes()


def scan(version_id: str, mode: str, token: str, student_id: str | None) -> None:
    pdf_meta = httpx.get(
        f"{BACKEND_URL}/versions/{version_id}/pdf",
        headers={"Authorization": f"Bearer {token}"},
    )
    if pdf_meta.status_code != 200:
        raise SystemExit(f"could not fetch version pdf metadata: {pdf_meta.status_code}")
    pdf_bytes = httpx.get(pdf_meta.json()["url"]).content
    _scan_from_pdf_bytes(version_id, pdf_bytes, mode, student_id, token)


def scan_url(version_id: str, pdf_url: str, mode: str, token: str, student_id: str | None) -> None:
    """Subtask 7b.4: scans a version whose signed download URL was obtained
    through the actual Next.js UI (the /quizzes/[id] page's real "Download
    PDF" links), not re-fetched via the API - so this step consumes exactly
    what a professor clicking that link would get."""
    pdf_bytes = httpx.get(pdf_url).content
    _scan_from_pdf_bytes(version_id, pdf_bytes, mode, student_id, token)


def _scan_from_pdf_bytes(
    version_id: str, pdf_bytes: bytes, mode: str, student_id: str | None, token: str
) -> None:
    mapping = _fetch_version_mapping(version_id)
    template = load_template()
    scan_headers = {"Authorization": f"Bearer {token}"}
    page_rgb = render_page_rgb(pdf_bytes, dpi=DPI)
    # A blank name field is its own confidence-gate flag (name_flagged) that
    # would route every scan here to needs_review regardless of the answer
    # marks below - specs asserting "finalized" after a clean/corrected scan
    # need a legible name written first, same as backend/tests/test_e2e_*.
    # Derived from student_id (title-cased, hyphens/underscores -> spaces)
    # rather than a fixed string: the results dashboard now shows
    # student_name ahead of student_id (see web/app/(app)/results/[id]/
    # page.tsx), so callers that identify a scanned row by its student_id
    # text (e.g. web/e2e/full-happy-path.spec.ts) need that same text to
    # actually appear on screen, and a hand-writable name needs to stay
    # OCR-friendly (Tesseract reads spaced words far more reliably than a
    # raw "student-id-style" hyphenated slug).
    display_name = (
        (student_id or "Web Regression Student").replace("-", " ").replace("_", " ").title()
    )
    write_name_on_page(page_rgb, template, display_name, dpi=DPI)

    if mode == "qr-unreadable":
        x0, y0, x1, y1 = qr_box_pixel_rect(template, DPI)
        page_rgb[y0:y1, x0:x1] = 255
        # No answers are marked - the request is expected to fail before
        # ever reaching version lookup/scoring, so their state is moot.
        params = {"student_id": student_id} if student_id else {}
        response = httpx.post(
            f"{BACKEND_URL}/scan",
            files={"file": ("scan.png", _page_to_upload_bytes(page_rgb), "image/png")},
            params=params,
            headers=scan_headers,
        )
        print(
            json.dumps(
                {
                    "status_code": response.status_code,
                    "body": (
                        response.json()
                        if response.headers.get("content-type", "").startswith("application/json")
                        else response.text
                    ),
                }
            )
        )
        return

    special_row_index: int | None = None
    special_kind: str | None = None
    if mode != "correct":
        special_kind, index_str = mode.split(":")
        special_row_index = int(index_str)

    for row_index, qid in enumerate(mapping["question_order"]):
        question = mapping["questions"][str(qid)]
        canonical_index = ord(question["correct_option"].upper()) - ord("A")
        permutation = mapping["option_order"][str(qid)]
        correct_shuffled_pos = permutation.index(canonical_index)

        if row_index == special_row_index and special_kind == "wrong":
            wrong_pos = (correct_shuffled_pos + 1) % len(permutation)
            _mark_filled(page_rgb, template, row_index, wrong_pos)
        elif row_index == special_row_index and special_kind == "ambiguous":
            _mark_ambiguous(page_rgb, template, row_index, correct_shuffled_pos)
        else:
            _mark_filled(page_rgb, template, row_index, correct_shuffled_pos)

    params = {"student_id": student_id} if student_id else {}
    response = httpx.post(
        f"{BACKEND_URL}/scan",
        files={"file": ("scan.png", _page_to_upload_bytes(page_rgb), "image/png")},
        params=params,
        headers=scan_headers,
    )
    response.raise_for_status()
    body = response.json()

    correct_option_for_flagged_row = None
    if special_row_index is not None:
        qid = mapping["question_order"][special_row_index]
        correct_option_for_flagged_row = mapping["questions"][str(qid)]["correct_option"]

    print(json.dumps({**body, "correct_option_for_flagged_row": correct_option_for_flagged_row}))


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    command = sys.argv[1]
    if command == "seed-quiz":
        seed_quiz(sys.argv[2])
    elif command == "scan":
        student_id = sys.argv[5] if len(sys.argv) > 5 else None
        scan(sys.argv[2], sys.argv[3], sys.argv[4], student_id)
    elif command == "scan-url":
        student_id = sys.argv[6] if len(sys.argv) > 6 else None
        scan_url(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], student_id)
    elif command == "token":
        print_token(sys.argv[2], sys.argv[3])
    else:
        raise SystemExit(f"unknown command: {command}")


if __name__ == "__main__":
    main()
