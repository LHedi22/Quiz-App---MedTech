"""Loads a quiz's questions and persists generated versions."""

from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Json

from app.models.version import QuestionForShuffle, ShuffledVersion


def get_questions_for_shuffle(conn: psycopg.Connection, quiz_id: UUID) -> list[QuestionForShuffle]:
    with conn.cursor() as cur:
        cur.execute(
            "select id, options, correct_option from questions "
            "where quiz_id = %s order by order_index",
            (quiz_id,),
        )
        rows = cur.fetchall()
    return [QuestionForShuffle(id=row[0], options=row[1], correct_option=row[2]) for row in rows]


def insert_versions(
    conn: psycopg.Connection, quiz_id: UUID, versions: list[ShuffledVersion]
) -> list[UUID]:
    """Insert all generated versions for one quiz as a single transaction.

    `qr_id` is a placeholder unique identifier for now (Phase 4 encodes the real
    QR image content); it only needs to be unique per version at this stage.
    """
    inserted_ids: list[UUID] = []
    with conn:
        with conn.cursor() as cur:
            for version in versions:
                cur.execute(
                    """
                    insert into versions
                        (quiz_id, version_number, qr_id, question_order, option_order)
                    values (%s, %s, %s, %s, %s)
                    returning id
                    """,
                    (
                        quiz_id,
                        version.version_number,
                        str(uuid4()),
                        Json([str(qid) for qid in version.question_order]),
                        Json(version.option_order),
                    ),
                )
                inserted_ids.append(cur.fetchone()[0])
    return inserted_ids
