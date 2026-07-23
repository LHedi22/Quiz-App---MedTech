"""Subtasks 6.1-6.3: version lookup, translate & score, confidence gate.

Uses the real Phase 1.3 demo seed data (`migrations/0003_seed_demo_data.sql`,
auto-loaded by `supabase/seed.sql` on `supabase start`) as the "known version
mapping" the DoD calls for: version `demo-quiz-v1` shuffles both question
order and every question's option order non-identically, so translating
through it exercises the hardest case, not a trivial identity permutation.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from app.db import DATABASE_URL
from app.models.scoring import DetectedAnswer
from app.services.scoring import lookup_version_by_qr_id, translate_and_score


def _db_reachable() -> bool:
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2):
            return True
    except psycopg.OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    not _db_reachable(),
    reason="local Postgres not reachable (run `supabase start` in /backend)",
)

DEMO_QUIZ_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
DEMO_VERSION_1_ID = uuid.UUID("00000000-0000-0000-0000-000000000021")
DEMO_QR_ID_V1 = "demo-quiz-v1"

# Canonical question ids by their order_index (1-based), from migration 0003.
Q1, Q2, Q3, Q4, Q5 = (
    uuid.UUID("00000000-0000-0000-0000-000000000011"),
    uuid.UUID("00000000-0000-0000-0000-000000000012"),
    uuid.UUID("00000000-0000-0000-0000-000000000013"),
    uuid.UUID("00000000-0000-0000-0000-000000000014"),
    uuid.UUID("00000000-0000-0000-0000-000000000015"),
)


def _connect() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL)


# ---------------------------------------------------------------------------
# Subtask 6.1 - version lookup
# ---------------------------------------------------------------------------


def test_lookup_valid_qr_id_returns_correct_version_and_question_data():
    with _connect() as conn:
        result = lookup_version_by_qr_id(conn, DEMO_QR_ID_V1)

    assert result is not None
    assert result.version.id == DEMO_VERSION_1_ID
    assert result.version.quiz_id == DEMO_QUIZ_ID
    # Non-identity: printed row order is not canonical question order.
    assert result.version.question_order == [Q3, Q1, Q5, Q2, Q4]
    assert result.version.question_order != sorted(result.version.question_order, key=str)

    assert set(result.questions_by_id.keys()) == {Q1, Q2, Q3, Q4, Q5}
    assert result.questions_by_id[Q1].order_index == 1
    assert result.questions_by_id[Q1].correct_option == "B"
    assert result.questions_by_id[Q3].correct_option == "C"

    # Non-identity option order for at least one question (not [0,1,2,3]).
    assert result.version.option_order[str(Q1)] != [0, 1, 2, 3]


def test_lookup_nonexistent_qr_id_returns_none_not_an_exception():
    with _connect() as conn:
        result = lookup_version_by_qr_id(conn, f"no-such-qr-{uuid.uuid4()}")
    assert result is None


# ---------------------------------------------------------------------------
# Subtask 6.2 - translate & score
# ---------------------------------------------------------------------------


def _clean_answer(
    position: int, filled_shuffled_index: int, num_options: int = 4
) -> DetectedAnswer:
    labels = ["empty"] * num_options
    labels[filled_shuffled_index] = "filled"
    confidences = [0.95] * num_options
    return DetectedAnswer(position=position, option_labels=labels, option_confidences=confidences)


def _correct_shuffled_position(lookup, question_id: uuid.UUID) -> int:
    """Independently derive (by searching the stored permutation, not by
    calling any scoring code) which shuffled position a student would need
    to fill to answer `question_id` correctly - the same
    `.index(canonical_index)` pattern already used in
    tests/test_versions_endpoint.py to verify shuffle output."""
    question = lookup.questions_by_id[question_id]
    canonical_correct_index = ord(question.correct_option) - ord("A")
    return lookup.version.option_order[str(question_id)].index(canonical_correct_index)


@pytest.fixture
def demo_v1_lookup():
    with _connect() as conn:
        result = lookup_version_by_qr_id(conn, DEMO_QR_ID_V1)
    assert result is not None
    return result


def test_all_correct_answer_set_matches_hand_calculated_score(demo_v1_lookup):
    detected = [
        _clean_answer(position, _correct_shuffled_position(demo_v1_lookup, qid))
        for position, qid in enumerate(demo_v1_lookup.version.question_order)
    ]

    result = translate_and_score(demo_v1_lookup, detected)

    assert result.status == "finalized"
    assert result.total_score == 5.0
    assert all(a.correct is True and a.score == 1.0 for a in result.answers)
    # detected_option is the canonical letter, matching questions.correct_option.
    for answer in result.answers:
        question = demo_v1_lookup.questions_by_id[answer.question_id]
        assert answer.detected_option == question.correct_option


def test_all_wrong_answer_set_matches_hand_calculated_score(demo_v1_lookup):
    detected = []
    for position, qid in enumerate(demo_v1_lookup.version.question_order):
        correct_position = _correct_shuffled_position(demo_v1_lookup, qid)
        wrong_position = (correct_position + 1) % 4  # every question here has 4 options
        detected.append(_clean_answer(position, wrong_position))

    result = translate_and_score(demo_v1_lookup, detected)

    assert result.status == "finalized"
    assert result.total_score == 0.0
    assert all(a.correct is False and a.score == 0.0 for a in result.answers)


def test_mixed_answer_set_matches_hand_calculated_score(demo_v1_lookup):
    # Q3 (position 0), Q5 (position 2), Q4 (position 4) correct;
    # Q1 (position 1), Q2 (position 3) wrong -> hand-calculated total = 3.0.
    correct_positions = {0, 2, 4}
    detected = []
    for position, qid in enumerate(demo_v1_lookup.version.question_order):
        correct_shuffled = _correct_shuffled_position(demo_v1_lookup, qid)
        if position in correct_positions:
            detected.append(_clean_answer(position, correct_shuffled))
        else:
            wrong_shuffled = (correct_shuffled + 1) % 4
            detected.append(_clean_answer(position, wrong_shuffled))

    result = translate_and_score(demo_v1_lookup, detected)

    assert result.status == "finalized"
    assert result.total_score == 3.0
    expected_correct_positions = {
        demo_v1_lookup.version.question_order[p]: True for p in correct_positions
    }
    for answer in result.answers:
        if answer.question_id in expected_correct_positions:
            assert answer.correct is True
        else:
            assert answer.correct is False


def test_translation_correctly_unshuffles_both_question_and_option_order(demo_v1_lookup):
    """Dedicated check for the hardest case called out by the DoD: question
    order AND option order are both non-identity permutations. Answers a
    single specific question (Q2, whose canonical option order is neither
    identity nor a fixed offset - option_order[Q2] = [2,0,3,1]) and confirms
    the exact canonical letter comes back, not just an aggregate score."""
    q2_position = demo_v1_lookup.version.question_order.index(Q2)
    assert demo_v1_lookup.version.option_order[str(Q2)] == [2, 0, 3, 1]

    # Shuffled position 1 -> canonical index 0 -> letter "A".
    detected = [_clean_answer(q2_position, filled_shuffled_index=1)]
    # Fill in the rest of the page with something unambiguous so the whole
    # submission still finalizes and we can read Q2's own result cleanly.
    for position, qid in enumerate(demo_v1_lookup.version.question_order):
        if position == q2_position:
            continue
        detected.append(_clean_answer(position, _correct_shuffled_position(demo_v1_lookup, qid)))

    result = translate_and_score(demo_v1_lookup, detected)
    q2_answer = next(a for a in result.answers if a.question_id == Q2)

    assert q2_answer.detected_option == "A"
    assert q2_answer.question_no == 2
    # Q2's correct_option is "C", so guessing "A" must be scored wrong.
    assert q2_answer.correct is False
    assert q2_answer.score == 0.0


# ---------------------------------------------------------------------------
# Subtask 6.3 - confidence gate
# ---------------------------------------------------------------------------


def test_all_high_confidence_single_mark_finalizes(demo_v1_lookup):
    detected = [
        _clean_answer(position, _correct_shuffled_position(demo_v1_lookup, qid))
        for position, qid in enumerate(demo_v1_lookup.version.question_order)
    ]
    result = translate_and_score(demo_v1_lookup, detected)
    assert result.status == "finalized"
    assert all(not a.flagged for a in result.answers)


def test_one_multi_mark_case_flags_only_that_answer(demo_v1_lookup):
    detected = [
        _clean_answer(position, _correct_shuffled_position(demo_v1_lookup, qid))
        for position, qid in enumerate(demo_v1_lookup.version.question_order)
    ]
    # Position 2 (Q5): mark two bubbles instead of one.
    detected[2] = DetectedAnswer(
        position=2,
        option_labels=["filled", "filled", "empty", "empty"],
        option_confidences=[0.95, 0.95, 0.95, 0.95],
    )

    result = translate_and_score(demo_v1_lookup, detected)

    assert result.status == "needs_review"
    assert result.total_score is None
    flagged_question_ids = {a.question_id for a in result.answers if a.flagged}
    assert flagged_question_ids == {Q5}
    for a in result.answers:
        if a.question_id != Q5:
            assert not a.flagged
            assert a.correct is True


def test_zero_marks_case_flags_only_that_answer(demo_v1_lookup):
    detected = [
        _clean_answer(position, _correct_shuffled_position(demo_v1_lookup, qid))
        for position, qid in enumerate(demo_v1_lookup.version.question_order)
    ]
    detected[1] = DetectedAnswer(
        position=1,
        option_labels=["empty", "empty", "empty", "empty"],
        option_confidences=[0.96, 0.96, 0.96, 0.96],
    )

    result = translate_and_score(demo_v1_lookup, detected)

    assert result.status == "needs_review"
    flagged_question_ids = {a.question_id for a in result.answers if a.flagged}
    assert flagged_question_ids == {Q1}  # position 1 -> Q1
    flagged_answer = next(a for a in result.answers if a.question_id == Q1)
    assert flagged_answer.detected_option is None
    assert flagged_answer.correct is None
    assert flagged_answer.score is None


def test_low_confidence_ambiguous_bubble_flags_only_that_answer(demo_v1_lookup):
    detected = [
        _clean_answer(position, _correct_shuffled_position(demo_v1_lookup, qid))
        for position, qid in enumerate(demo_v1_lookup.version.question_order)
    ]
    # Position 4 (Q4): a single mark, but the classifier itself called it
    # "ambiguous" (below-threshold confidence) rather than confidently filled.
    correct_shuffled = _correct_shuffled_position(demo_v1_lookup, Q4)
    labels = ["empty"] * 4
    labels[correct_shuffled] = "ambiguous"
    detected[4] = DetectedAnswer(position=4, option_labels=labels, option_confidences=[0.6] * 4)

    result = translate_and_score(demo_v1_lookup, detected)

    assert result.status == "needs_review"
    flagged_question_ids = {a.question_id for a in result.answers if a.flagged}
    assert flagged_question_ids == {Q4}
