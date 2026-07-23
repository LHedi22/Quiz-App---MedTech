"""Quiz CRUD for the Phase 7 web app: create, list-mine, and list-versions.

Ownership is enforced at the API layer (per `app/db.py`'s documented "RLS is
bypassed by the trusted backend, ownership is enforced here" plan): every
route requires a verified Supabase JWT, and any lookup by id is scoped to
`owner_id = current_user.id` so one professor can never see another's quiz.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.db import get_connection
from app.models.quiz import QuizCreateRequest
from app.services.auth import AuthUser, ensure_user_row, get_current_user
from app.services.submissions import list_submissions_for_quiz

router = APIRouter()


def _serialize_submission_summary(row: dict) -> dict:
    return {
        **row,
        "id": str(row["id"]),
        "version_id": str(row["version_id"]),
        "created_at": row["created_at"].isoformat(),
    }


@router.post("/quizzes", status_code=201)
async def create_quiz(
    request: QuizCreateRequest, user: AuthUser = Depends(get_current_user)
) -> dict:
    with get_connection() as conn:
        ensure_user_row(conn, user)
        with conn.cursor() as cur:
            cur.execute(
                "insert into quizzes (owner_id, title) values (%s, %s) returning id, created_at",
                (user.id, request.title),
            )
            quiz_id, created_at = cur.fetchone()
        conn.commit()
    return {"id": str(quiz_id), "title": request.title, "created_at": created_at.isoformat()}


@router.get("/quizzes")
async def list_quizzes(user: AuthUser = Depends(get_current_user)) -> list[dict]:
    with get_connection() as conn:
        ensure_user_row(conn, user)
        with conn.cursor() as cur:
            cur.execute(
                "select id, title, created_at from quizzes "
                "where owner_id = %s order by created_at desc",
                (user.id,),
            )
            rows = cur.fetchall()
    return [{"id": str(row[0]), "title": row[1], "created_at": row[2].isoformat()} for row in rows]


def _get_owned_quiz_id(conn, quiz_id: UUID, user: AuthUser) -> None:
    with conn.cursor() as cur:
        cur.execute("select id from quizzes where id = %s and owner_id = %s", (quiz_id, user.id))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"quiz {quiz_id} not found")


@router.get("/quizzes/{quiz_id}/versions")
async def list_quiz_versions(
    quiz_id: UUID, user: AuthUser = Depends(get_current_user)
) -> list[dict]:
    with get_connection() as conn:
        ensure_user_row(conn, user)
        _get_owned_quiz_id(conn, quiz_id, user)
        with conn.cursor() as cur:
            cur.execute(
                "select id, version_number from versions "
                "where quiz_id = %s order by version_number",
                (quiz_id,),
            )
            rows = cur.fetchall()
    return [{"id": str(row[0]), "version_number": row[1]} for row in rows]


@router.get("/quizzes/{quiz_id}/submissions")
async def list_quiz_submissions(
    quiz_id: UUID,
    status: str | None = None,
    user: AuthUser = Depends(get_current_user),
) -> list[dict]:
    with get_connection() as conn:
        ensure_user_row(conn, user)
        _get_owned_quiz_id(conn, quiz_id, user)
        rows = list_submissions_for_quiz(conn, quiz_id, status)
    return [_serialize_submission_summary(row) for row in rows]
