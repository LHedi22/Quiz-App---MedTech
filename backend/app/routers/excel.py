from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from app.db import get_connection
from app.models.question import ParseError
from app.services.auth import AuthUser, ensure_user_row, get_current_user
from app.services.parsing import parse_quiz_excel
from app.services.questions import insert_questions

router = APIRouter()


def _get_owned_quiz_id(conn, quiz_id: UUID, user: AuthUser) -> None:
    with conn.cursor() as cur:
        cur.execute("select id from quizzes where id = %s and owner_id = %s", (quiz_id, user.id))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"quiz {quiz_id} not found")


@router.post("/quizzes/{quiz_id}/upload", status_code=201)
async def upload_quiz_excel(
    quiz_id: UUID, file: UploadFile, user: AuthUser = Depends(get_current_user)
) -> dict:
    contents = await file.read()
    result = parse_quiz_excel(BytesIO(contents))

    if isinstance(result, ParseError):
        raise HTTPException(status_code=422, detail=result.model_dump())

    questions = result

    with get_connection() as conn:
        ensure_user_row(conn, user)
        _get_owned_quiz_id(conn, quiz_id, user)
        insert_questions(conn, quiz_id, questions)

    return {"quiz_id": str(quiz_id), "questions_inserted": len(questions)}
