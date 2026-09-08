"""Subtasks 6.1-6.3: version lookup, translate & score detected answers, and
the confidence gate deciding whether a submission auto-finalizes.

CLAUDE.md Section 2 rule 5 is the concrete confidence-gate spec: never
auto-finalize when a QR is unreadable (handled *before* this module is ever
called - see app/routers/scan.py, which never calls into this module unless
a qr_id was successfully decoded), or per-question when zero bubbles are
filled, multiple bubbles are filled, or the classifier's confidence falls
below its threshold. Any one flagged answer routes the whole submission to
`needs_review`; only an all-clean set of answers is `finalized`.
"""

from __future__ import annotations

from collections.abc import Iterable
from string import ascii_uppercase
from uuid import UUID

import psycopg

from app.models.scoring import (
    DetectedAnswer,
    QuestionForScoring,
    ScoredAnswer,
    ScoringResult,
    VersionForScoring,
    VersionLookupResult,
)


def lookup_version_by_qr_id(conn: psycopg.Connection, qr_id: str) -> VersionLookupResult | None:
    """Fetch the version + canonical question data a scanned QR code maps to.

    Returns None - never raises - if no version has this qr_id: a distinct,
    clearly-surfaced outcome (a corrupted scan or a QR from an unrelated
    quiz), not conflated with any other failure mode or a silent default.
    """
    with conn.cursor() as cur:
        cur.execute(
            "select id, quiz_id, question_order, option_order from versions where qr_id = %s",
            (qr_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        version_id, quiz_id, question_order, option_order = row
        question_ids = [UUID(qid) for qid in question_order]

        cur.execute(
            "select id, order_index, correct_option from questions where id = any(%s)",
            (question_ids,),
        )
        questions_by_id = {
            r[0]: QuestionForScoring(id=r[0], order_index=r[1], correct_option=r[2])
            for r in cur.fetchall()
        }

    version = VersionForScoring(
        id=version_id,
        quiz_id=quiz_id,
        question_order=question_ids,
        option_order=option_order,
    )
    return VersionLookupResult(version=version, questions_by_id=questions_by_id)


# The per-question weight. Every question is worth this today; a future
# weighted or negative-marking scheme changes it here once and BOTH the scan
# pipeline and the professor-correction path (submissions.py) follow, rather
# than each re-hardcoding 1.0/0.0 and silently diverging.
CORRECT_SCORE = 1.0
INCORRECT_SCORE = 0.0


def score_answer(marked_option: str | None, key_option: str | None) -> tuple[bool, float]:
    """Score one answer against the master key. A blank (`marked_option is
    None`) is never correct. Shared by `translate_and_score` (scan path) and
    `submissions.apply_manual_correction` (professor edit) so the weight and
    the correctness rule live in exactly one place."""
    correct = marked_option is not None and marked_option == key_option
    return correct, CORRECT_SCORE if correct else INCORRECT_SCORE


def sum_answer_scores(scores: Iterable[float | None]) -> float:
    """Total of an answer set's per-question scores. A missing score counts
    as 0 - a professor-blanked answer stores 0.0 explicitly; this also
    guards a stray NULL from becoming a TypeError. Shared by the scan path
    and `submissions._recompute_submission_status`."""
    return sum(s or 0.0 for s in scores)


def _status_for(answers: list[ScoredAnswer]) -> str:
    return "needs_review" if any(a.flagged for a in answers) else "finalized"


def _total_score(answers: list[ScoredAnswer], status: str) -> float | None:
    if status != "finalized":
        return None
    return sum_answer_scores(a.score for a in answers)


def translate_and_score(
    lookup: VersionLookupResult, detected_answers: list[DetectedAnswer]
) -> ScoringResult:
    """Un-shuffle each detected position back to a canonical question/option,
    score it against the master key, and apply the confidence gate.

    Un-shuffling a position needs both permutations independently:
    `question_order[position]` recovers *which* canonical question this row
    was, and `option_order[question_id][shuffled_option_index]` recovers
    *which* canonical option a filled bubble at that shuffled position
    corresponds to. Getting either inversion wrong scores against the wrong
    answer key even when the other is correct, so this is deliberately
    exercised against a version where both orders are non-identity
    permutations in `tests/test_scoring.py`, not just the trivial case.
    """
    answers: list[ScoredAnswer] = []

    for detected in sorted(detected_answers, key=lambda d: d.position):
        question_id = lookup.version.question_order[detected.position]
        question = lookup.questions_by_id[question_id]
        canonical_indices = lookup.version.option_order[str(question_id)]

        filled_positions = [
            i for i, label in enumerate(detected.option_labels) if label == "filled"
        ]
        any_ambiguous = any(label == "ambiguous" for label in detected.option_labels)
        confidence = min(detected.option_confidences) if detected.option_confidences else 0.0

        # Confidence gate (CLAUDE.md Section 2 rule 5): flag on zero marks,
        # multiple marks, or any bubble the classifier itself couldn't
        # confidently call - regardless of which class it leaned toward.
        flagged = any_ambiguous or len(filled_positions) != 1

        detected_option = None
        if len(filled_positions) == 1:
            canonical_index = canonical_indices[filled_positions[0]]
            detected_option = ascii_uppercase[canonical_index]

        correct = None
        score = None
        if not flagged:
            correct, score = score_answer(detected_option, question.correct_option)

        answers.append(
            ScoredAnswer(
                question_no=question.order_index,
                question_id=question_id,
                detected_option=detected_option,
                confidence=confidence,
                flagged=flagged,
                correct=correct,
                score=score,
            )
        )

    status = _status_for(answers)
    total_score = _total_score(answers, status)
    return ScoringResult(total_score=total_score, status=status, answers=answers)
