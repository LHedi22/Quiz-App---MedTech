from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.db import get_connection
from app.models.version import VersionCreateRequest
from app.services.shuffler import generate_versions
from app.services.versions import get_questions_for_shuffle, insert_versions

router = APIRouter()


@router.post("/quizzes/{quiz_id}/versions", status_code=201)
async def create_versions(quiz_id: UUID, request: VersionCreateRequest) -> dict:
    if request.count < 1:
        raise HTTPException(status_code=400, detail="count must be at least 1")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("select id from quizzes where id = %s", (quiz_id,))
            if cur.fetchone() is None:
                raise HTTPException(status_code=404, detail=f"quiz {quiz_id} not found")

        questions = get_questions_for_shuffle(conn, quiz_id)
        if not questions:
            raise HTTPException(status_code=400, detail="quiz has zero questions")

        versions = generate_versions(questions, request.count)
        version_ids = insert_versions(conn, quiz_id, versions)

    return {"quiz_id": str(quiz_id), "versions_created": len(version_ids)}
