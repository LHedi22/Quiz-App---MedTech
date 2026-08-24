"""Subtask 6.4: the scan endpoint tying together the whole Phase 5/6
pipeline (decode QR -> lookup version -> align -> extract bubbles -> classify
-> translate -> score -> confidence gate -> persist), plus the
professor-review endpoints for flagged submissions.

Scope note: every question is rendered with exactly 4 options (the Excel
upload format is a fixed question_text/option_a-d/correct_option layout, see
docs/EXCEL_FORMAT.md), so bubble extraction always uses NUM_OPTIONS = 4. A
version whose questions span more than one printed page (`questions_per_page`
in pdf_template.json, currently 12) isn't scoreable from a single scanned
image yet - stitching multiple photos of the same submission together is
left for a later phase (the mobile batch-scan flow, Phase 8) rather than
guessed at here; /scan surfaces that case as a clear 501, not a silent
mis-score.
"""

from __future__ import annotations

from uuid import UUID

import cv2
import numpy as np
from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile

from app.db import get_connection
from app.ml.omr.align import align_page
from app.ml.omr.classify import classify_bubble
from app.ml.omr.extract import extract_bubble_crops
from app.ml.omr.name_ocr import detect_name
from app.ml.omr.qr_decode import decode_qr_from_page
from app.models.scoring import DetectedAnswer
from app.services import submissions as submissions_service
from app.services.auth import AuthUser, ensure_user_row, get_current_user
from app.services.pdf_gen import load_template
from app.services.scoring import lookup_version_by_qr_id, translate_and_score

router = APIRouter()

DPI = 200
NUM_OPTIONS = 4


def _detect_answers_on_page(
    aligned_image: np.ndarray, template: dict, num_questions: int
) -> list[DetectedAnswer]:
    crops = extract_bubble_crops(aligned_image, template, num_questions, NUM_OPTIONS, dpi=DPI)
    by_row: dict[int, list] = {}
    for crop in crops:
        by_row.setdefault(crop.row_index, []).append(crop)

    detected: list[DetectedAnswer] = []
    for row_index in sorted(by_row):
        row_crops = sorted(by_row[row_index], key=lambda c: c.option_index)
        labels: list[str] = []
        confidences: list[float] = []
        for crop in row_crops:
            label, confidence = classify_bubble(crop.image)
            labels.append(label)
            confidences.append(confidence)
        detected.append(
            DetectedAnswer(position=row_index, option_labels=labels, option_confidences=confidences)
        )
    return detected


@router.post("/scan", status_code=201)
async def scan_submission(
    file: UploadFile, student_id: str | None = None, capture_id: str | None = None
) -> dict:
    contents = await file.read()
    image_array = np.frombuffer(contents, dtype=np.uint8)
    bgr = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if bgr is None:
        raise HTTPException(status_code=422, detail={"error": "unreadable_image"})
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

    template = load_template()

    # QR unreadable is a distinct failure mode: it never reaches version
    # lookup or scoring at all, and no submission row is ever created for it -
    # it must not be silently treated as an ordinary needs_review submission.
    qr_id = decode_qr_from_page(rgb, template, dpi=DPI)
    if qr_id is None:
        raise HTTPException(status_code=422, detail={"error": "qr_unreadable"})

    with get_connection() as conn:
        lookup = lookup_version_by_qr_id(conn, qr_id)
        if lookup is None:
            raise HTTPException(
                status_code=404, detail={"error": "version_not_found", "qr_id": qr_id}
            )

        num_questions = len(lookup.version.question_order)
        if num_questions > template["questions_per_page"]:
            raise HTTPException(
                status_code=501,
                detail={"error": "multi_page_not_supported", "num_questions": num_questions},
            )

        alignment = align_page(rgb, template, dpi=DPI)
        if not alignment.success:
            raise HTTPException(
                status_code=422, detail={"error": "alignment_failed", "message": alignment.error}
            )

        detected_answers = _detect_answers_on_page(alignment.warped_image, template, num_questions)
        result = translate_and_score(lookup, detected_answers)
        name_result = detect_name(alignment.warped_image, template, dpi=DPI)

        submission = submissions_service.create_submission(
            conn, lookup.version.id, result, name_result, student_id, capture_id
        )

    return {
        "submission_id": str(submission.id),
        "status": submission.status,
        "total_score": submission.total_score,
        "student_name": submission.student_name,
        "name_flagged": submission.name_flagged,
        "flagged_question_numbers": sorted(a.question_no for a in result.answers if a.flagged),
    }


def _serialize_submission_summary(row: dict) -> dict:
    return {
        **row,
        "id": str(row["id"]),
        "version_id": str(row["version_id"]),
        "created_at": row["created_at"].isoformat(),
    }


def _serialize_submission_detail(row: dict) -> dict:
    serialized = _serialize_submission_summary(row)
    serialized["answers"] = [{**a, "id": str(a["id"])} for a in row["answers"]]
    return serialized


@router.get("/submissions")
async def list_submissions(status: str = "needs_review") -> list[dict]:
    with get_connection() as conn:
        rows = submissions_service.list_submissions_by_status(conn, status)
    return [_serialize_submission_summary(row) for row in rows]


def _require_submission_owner(conn, submission_id: UUID, user: AuthUser) -> None:
    """404s (not a leaked 401/403) if the submission doesn't exist or belongs
    to another professor's quiz - the web app's review screens are the only
    caller of the two routes below, and both must never let one professor
    read or correct another's student answers (see CLAUDE.md Section 4).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            select q.owner_id from submissions s
            join versions v on v.id = s.version_id
            join quizzes q on q.id = v.quiz_id
            where s.id = %s
            """,
            (submission_id,),
        )
        row = cur.fetchone()
        if row is None or row[0] != user.id:
            raise HTTPException(status_code=404, detail=f"submission {submission_id} not found")


@router.get("/submissions/{submission_id}")
async def get_submission(submission_id: UUID, user: AuthUser = Depends(get_current_user)) -> dict:
    with get_connection() as conn:
        ensure_user_row(conn, user)
        _require_submission_owner(conn, submission_id, user)
        row = submissions_service.get_submission_with_answers(conn, submission_id)
    return _serialize_submission_detail(row)


@router.patch("/submissions/{submission_id}/answers/{answer_id}")
async def correct_answer(
    submission_id: UUID,
    answer_id: UUID,
    correct_option: str = Body(embed=True),
    user: AuthUser = Depends(get_current_user),
) -> dict:
    with get_connection() as conn:
        ensure_user_row(conn, user)
        _require_submission_owner(conn, submission_id, user)
        updated = submissions_service.apply_manual_correction(
            conn, submission_id, answer_id, correct_option.strip().upper()
        )
    if updated is None:
        raise HTTPException(status_code=404, detail="answer not found for this submission")
    return _serialize_submission_detail(updated)


@router.patch("/submissions/{submission_id}/name")
async def correct_name(
    submission_id: UUID,
    student_name: str = Body(embed=True),
    user: AuthUser = Depends(get_current_user),
) -> dict:
    with get_connection() as conn:
        ensure_user_row(conn, user)
        _require_submission_owner(conn, submission_id, user)
        updated = submissions_service.apply_name_correction(
            conn, submission_id, student_name.strip()
        )
    if updated is None:
        raise HTTPException(status_code=404, detail="submission not found")
    return _serialize_submission_detail(updated)
