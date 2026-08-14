"""Persists scan/grade results and backs the professor-review workflow
(Subtask 6.4): create a submission + its answers from a `ScoringResult`,
list submissions needing review, and apply a professor's manual correction
to a flagged answer or a flagged/misread student name.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import psycopg

from app.ml.omr.name_ocr import NameDetectionResult
from app.models.scoring import ScoringResult


@dataclass
class CreatedSubmission:
    id: UUID
    status: str
    total_score: float | None
    student_name: str | None
    name_flagged: bool


def create_submission(
    conn: psycopg.Connection,
    version_id: UUID,
    result: ScoringResult,
    name_result: NameDetectionResult,
    student_id: str | None = None,
) -> CreatedSubmission:
    """Insert a submission and all of its answers as a single transaction.

    A submission's overall status is `needs_review` if *either* gate trips -
    a flagged answer or a flagged (low-confidence/illegible) name read - not
    just answers (CLAUDE.md Section 2 rule 5's confidence gate applies to
    every OMR-adjacent detection, name reading included). total_score is
    still persisted even when only the name is flagged: the answer score
    itself is genuinely known, only the student's identity isn't confirmed
    yet.

    Returns the fields the caller needs rather than just the id: this
    function's `with conn:` block commits *and closes* `conn` (this
    project's psycopg3 usage - see apply_manual_correction's docstring for
    the same note), so callers can't reuse `conn` afterward to look the row
    back up.
    """
    status = (
        "needs_review" if (result.status == "needs_review" or name_result.flagged) else "finalized"
    )
    student_name = name_result.text or None

    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into submissions
                    (version_id, student_id, student_name, name_confidence,
                     name_flagged, total_score, status)
                values (%s, %s, %s, %s, %s, %s, %s)
                returning id
                """,
                (
                    version_id,
                    student_id,
                    student_name,
                    name_result.confidence,
                    name_result.flagged,
                    result.total_score,
                    status,
                ),
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
    return CreatedSubmission(
        id=submission_id,
        status=status,
        total_score=result.total_score,
        student_name=student_name,
        name_flagged=name_result.flagged,
    )


_SUBMISSION_COLUMNS = (
    "id, version_id, student_id, student_name, name_confidence, name_flagged, "
    "total_score, status, created_at"
)


def get_submission_with_answers(conn: psycopg.Connection, submission_id: UUID) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            f"select {_SUBMISSION_COLUMNS} from submissions where id = %s",
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
            f"select {_SUBMISSION_COLUMNS} from submissions where status = %s order by created_at",
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
    prefixed_columns = ", ".join(f"s.{c.strip()}" for c in _SUBMISSION_COLUMNS.split(","))
    with conn.cursor() as cur:
        cur.execute(
            f"""
            select {prefixed_columns}
            from submissions s
            join versions v on v.id = s.version_id
            where v.quiz_id = %s and (%s::text is null or s.status = %s)
            order by s.created_at
            """,
            (quiz_id, status, status),
        )
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _recompute_submission_status(cur: psycopg.Cursor, submission_id: UUID) -> None:
    """Shared by apply_manual_correction and apply_name_correction: a
    submission only finalizes once *both* confidence gates are clear - no
    flagged answers and a non-flagged name read (CLAUDE.md Section 2 rule
    5 applies to every OMR-adjacent detection, not just bubbles)."""
    cur.execute("select flagged from answers where submission_id = %s", (submission_id,))
    any_answer_flagged = any(r[0] for r in cur.fetchall())

    cur.execute("select name_flagged from submissions where id = %s", (submission_id,))
    name_flagged = cur.fetchone()[0]

    if any_answer_flagged or name_flagged:
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

        _recompute_submission_status(cur, submission_id)

    conn.commit()
    return get_submission_with_answers(conn, submission_id)


def apply_name_correction(
    conn: psycopg.Connection,
    submission_id: UUID,
    student_name: str,
) -> dict | None:
    """A professor manually confirms/corrects a flagged (or misread) student
    name: sets student_name, clears name_flagged, and - if every answer is
    also resolved - finalizes the submission, same as apply_manual_correction
    does for answers.

    Returns None if the submission doesn't exist (checkable, not silent).
    """
    with conn.cursor() as cur:
        cur.execute("select id from submissions where id = %s", (submission_id,))
        if cur.fetchone() is None:
            return None

        cur.execute(
            "update submissions set student_name = %s, name_flagged = false where id = %s",
            (student_name, submission_id),
        )

        _recompute_submission_status(cur, submission_id)

    conn.commit()
    return get_submission_with_answers(conn, submission_id)
