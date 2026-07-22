from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, HTTPException, UploadFile

from app.db import get_connection
from app.models.question import ParseError
from app.services.parsing import parse_quiz_excel
from app.services.questions import insert_questions

router = APIRouter()


@router.post("/quizzes/{quiz_id}/upload", status_code=201)
async def upload_quiz_excel(quiz_id: UUID, file: UploadFile) -> dict:
    contents = await file.read()
    result = parse_quiz_excel(BytesIO(contents))

    if isinstance(result, ParseError):
        raise HTTPException(status_code=422, detail=result.model_dump())

    questions = result

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("select id from quizzes where id = %s", (quiz_id,))
            if cur.fetchone() is None:
                raise HTTPException(status_code=404, detail=f"quiz {quiz_id} not found")

        insert_questions(conn, quiz_id, questions)

    return {"quiz_id": str(quiz_id), "questions_inserted": len(questions)}
