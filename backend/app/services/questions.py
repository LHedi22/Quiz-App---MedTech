"""Persists parsed questions for a quiz inside a single all-or-nothing transaction."""

from uuid import UUID

import psycopg
from psycopg.types.json import Json

from app.models.question import QuestionSchema


def insert_questions(
    conn: psycopg.Connection, quiz_id: UUID, questions: list[QuestionSchema]
) -> None:
    """Insert all rows for one quiz upload as a single transaction.

    Relies on psycopg's connection context manager: if any statement in this
    block raises, `with conn:` rolls back the *entire* transaction on exit
    rather than leaving earlier successful inserts committed.
    """
    with conn:
        with conn.cursor() as cur:
            for question in questions:
                cur.execute(
                    """
                    insert into questions (quiz_id, text, options, correct_option, order_index)
                    values (%s, %s, %s, %s, %s)
                    """,
                    (
                        quiz_id,
                        question.text,
                        Json(question.options),
                        question.correct_option,
                        question.order_index,
                    ),
                )
