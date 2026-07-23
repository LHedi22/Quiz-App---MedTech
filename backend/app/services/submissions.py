"""Persists scan/grade results and backs the professor-review workflow
(Subtask 6.4): create a submission + its answers from a `ScoringResult`,
list submissions needing review, and apply a professor's manual correction
to a flagged answer.
"""

from __future__ import annotations

from uuid import UUID

import psycopg

from app.models.scoring import ScoringResult


def create_submission(
    conn: psycopg.Connection,
    version_id: UUID,
    result: ScoringResult,
    student_id: str | None = None,
) -> UUID:
    """Insert a submission and all of its answers as a single transaction."""
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into submissions (version_id, student_id, total_score, status)
                values (%s, %s, %s, %s)
                returning id
                """,
                (version_id, student_id, result.total_score, result.status),
            )
            submission_id = cur.fetchone()[0]

            for answer in result.answers:
                cur.execute(
                    """
                    insert into answers
                        (submission_id, question_no, detected_option, confidence,
                         flagged, correct, score)
                    values (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        submission_id,
                        answer.question_no,
                        answer.detected_option,
                        answer.confidence,
                        answer.flagged,
                        answer.correct,
                        answer.score,
                    ),
                )
    return submission_id


def get_submission_with_answers(conn: psycopg.Connection, submission_id: UUID) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            "select id, version_id, student_id, total_score, status, created_at "
            "from submissions where id = %s",
            (submission_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        cols = [c.name for c in cur.description]
        submission = dict(zip(cols, row))

        cur.execute(
            "select id, question_no, detected_option, confidence, flagged, correct, score "
            "from answers where submission_id = %s order by question_no",
            (submission_id,),
        )
        cols = [c.name for c in cur.description]
        submission["answers"] = [dict(zip(cols, r)) for r in cur.fetchall()]
    return submission


def list_submissions_by_status(conn: psycopg.Connection, status: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            "select id, version_id, student_id, total_score, status, created_at "
            "from submissions where status = %s order by created_at",
            (status,),
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def list_submissions_for_quiz(
    conn: psycopg.Connection, quiz_id: UUID, status: str | None
) -> list[dict]:
    """Lists submissions for one quiz (joined through `versions.quiz_id`),
    optionally filtered by status - backs the Phase 7 results dashboard,
    which needs every status (mixed, not just `needs_review`) for a single
    quiz, unlike `list_submissions_by_status`'s single-status/all-quizzes
    scan-review queue.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            select s.id, s.version_id, s.student_id, s.total_score, s.status, s.created_at
            from submissions s
            join versions v on v.id = s.version_id
            where v.quiz_id = %s and (%s::text is null or s.status = %s)
            order by s.created_at
            """,
            (quiz_id, status, status),
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def apply_manual_correction(
    conn: psycopg.Connection,
    submission_id: UUID,
    answer_id: UUID,
    correct_option: str,
) -> dict | None:
    """A professor manually sets the correct detected option on a flagged
    answer: recomputes that answer's correct/score against the quiz's master
    key, un-flags it, and - if every answer on the submission is now
    resolved - flips the submission's status to finalized and recomputes its
    total_score.

    Returns None if the answer doesn't belong to that submission (a distinct,
    checkable outcome rather than silently updating the wrong row).

    Deliberately does not wrap its writes in `with conn:` - that context
    manager form closes the underlying connection on exit (not just the
    transaction), which would break the final read-back below and any
    caller that keeps using `conn` afterward. Callers own the connection's
    lifetime (see app/routers/scan.py), so this commits explicitly instead.
    """
    with conn.cursor() as cur:
        cur.execute(
            "select question_no from answers where id = %s and submission_id = %s",
            (answer_id, submission_id),
        )
        row = cur.fetchone()
        if row is None:
            return None
        question_no = row[0]

        cur.execute(
            """
            select q.correct_option
            from submissions s
            join versions v on v.id = s.version_id
            join questions q on q.quiz_id = v.quiz_id and q.order_index = %s
            where s.id = %s
            """,
            (question_no, submission_id),
        )
        expected = cur.fetchone()[0]

        correct = correct_option == expected
        score = 1.0 if correct else 0.0
        cur.execute(
            """
            update answers
            set detected_option = %s, correct = %s, score = %s, flagged = false
            where id = %s
            """,
            (correct_option, correct, score, answer_id),
        )

        cur.execute("select flagged from answers where submission_id = %s", (submission_id,))
        still_flagged = any(r[0] for r in cur.fetchall())

        if still_flagged:
            cur.execute(
                "update submissions set status = 'needs_review' where id = %s",
                (submission_id,),
            )
        else:
            cur.execute("select score from answers where submission_id = %s", (submission_id,))
            total = sum(r[0] for r in cur.fetchall())
            cur.execute(
                "update submissions set status = 'finalized', total_score = %s where id = %s",
                (total, submission_id),
            )

    conn.commit()
    return get_submission_with_answers(conn, submission_id)
