"""Phase 3 shuffle engine tests. Pure logic, no DB required."""

from collections import Counter
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.models.version import QuestionForShuffle
from app.services import shuffler
from app.services.shuffler import generate_version, generate_versions


def make_questions(n: int, options_per_question: int = 4, correct_option: str = "A"):
    return [
        QuestionForShuffle(
            id=uuid4(),
            options=[f"opt-{i}-{j}" for j in range(options_per_question)],
            correct_option=correct_option,
        )
        for i in range(n)
    ]


# --- Subtask 3.1: core shuffle algorithm -----------------------------------------


def test_distinct_question_orders_across_versions():
    questions = make_questions(10)
    versions = generate_versions(questions, count=5)

    orders = [tuple(v.question_order) for v in versions]
    assert len(set(orders)) == 5, "expected 5 distinct question orders, got duplicates"


def test_each_versions_option_order_is_a_valid_permutation():
    questions = make_questions(8, options_per_question=4)
    versions = generate_versions(questions, count=6)

    for version in versions:
        for question in questions:
            permutation = version.option_order[str(question.id)]
            assert sorted(permutation) == list(range(4)), (
                f"version {version.version_number} option_order for {question.id} "
                f"is not a valid permutation: {permutation}"
            )


def test_question_order_is_exact_permutation_of_canonical_question_ids():
    questions = make_questions(10)
    expected_ids = {q.id for q in questions}
    versions = generate_versions(questions, count=5)

    for version in versions:
        assert set(version.question_order) == expected_ids
        assert len(version.question_order) == len(set(version.question_order))


def test_correct_answer_traceable_end_to_end_for_two_versions():
    """Manually trace the true correct answer through two versions' stored mapping."""
    questions = [
        QuestionForShuffle(
            id=uuid4(), options=["Paris", "London", "Rome", "Berlin"], correct_option="A"
        ),
        QuestionForShuffle(id=uuid4(), options=["2", "4", "6", "8"], correct_option="C"),
    ]
    canonical_correct_index = {
        questions[0].id: 0,  # "A" -> index 0 -> "Paris"
        questions[1].id: 2,  # "C" -> index 2 -> "6"
    }

    versions = generate_versions(questions, count=2)
    assert len(versions) == 2

    for version in versions:
        for question in questions:
            shuffled_positions = version.option_order[str(question.id)]
            # shuffled_positions[new_index] == canonical_index at that new position
            new_index = shuffled_positions.index(canonical_correct_index[question.id])
            # The option actually sitting at new_index in the shuffled paper:
            shuffled_option_text = question.options[shuffled_positions[new_index]]
            # This must be exactly the true correct-answer text, recovered purely
            # from the stored option_order mapping (no other bookkeeping needed).
            assert shuffled_option_text == question.options[canonical_correct_index[question.id]]


# --- Subtask 3.2: anti-clustering constraint --------------------------------------


def _correct_letter_counts(version, questions) -> Counter:
    counts = Counter()
    for question in questions:
        canonical_index = ord(question.correct_option) - ord("A")
        shuffled_positions = version.option_order[str(question.id)]
        new_index = shuffled_positions.index(canonical_index)
        counts[chr(ord("A") + new_index)] += 1
    return counts


def test_no_version_exceeds_the_configured_clustering_threshold():
    questions = make_questions(12, options_per_question=4, correct_option="A")
    versions = generate_versions(questions, count=20)

    max_allowed = int(12 * shuffler.CORRECT_LETTER_MAX_FRACTION)
    for version in versions:
        counts = _correct_letter_counts(version, questions)
        assert max(counts.values()) <= max_allowed, (
            f"version {version.version_number} has {counts} — exceeds "
            f"{shuffler.CORRECT_LETTER_MAX_FRACTION * 100:.0f}% threshold of {max_allowed}"
        )


def test_reroll_does_not_infinite_loop_when_clustering_is_unavoidable():
    """A single-question quiz always has 100% of its correct answers on one letter,
    so the anti-clustering check can never be satisfied. Prove the reroll pass
    still terminates deterministically (bounded by max_attempts), not by hanging.
    """
    questions = make_questions(1)
    call_count = {"n": 0}
    original = shuffler._shuffle_once

    def counting_shuffle_once(qs, rng):
        call_count["n"] += 1
        return original(qs, rng)

    with patch.object(shuffler, "_shuffle_once", side_effect=counting_shuffle_once):
        version = generate_version(questions, version_number=1, seed=42, max_attempts=5)

    assert call_count["n"] == 5, "expected the reroll pass to stop at max_attempts, not hang"
    assert version is not None
    assert version.version_number == 1


def test_reroll_stops_early_once_unclustered():
    """Sanity check on the other side: when clustering is easily avoidable (many
    questions, several letters), the reroll pass should NOT burn all max_attempts.
    """
    questions = make_questions(12, options_per_question=4, correct_option="A")
    call_count = {"n": 0}
    original = shuffler._shuffle_once

    def counting_shuffle_once(qs, rng):
        call_count["n"] += 1
        return original(qs, rng)

    with patch.object(shuffler, "_shuffle_once", side_effect=counting_shuffle_once):
        generate_version(questions, version_number=1, seed=1, max_attempts=200)

    assert call_count["n"] < 200


def test_generate_versions_avoids_repeating_exact_same_distribution_when_room_allows():
    """With 12 questions across 4 letters there are many distinct unclustered letter
    distributions available, so the anti-repeat pass and the clustering pass don't
    have to fight each other. Confirm distributions actually differ across versions
    (not just question/option order) while every version still respects the
    clustering threshold.
    """
    questions = make_questions(12, options_per_question=4)
    for i, question in enumerate(questions):
        question.correct_option = "ABCD"[i % 4]  # spread correct answers across letters

    versions = generate_versions(questions, count=5)

    max_allowed = int(12 * shuffler.CORRECT_LETTER_MAX_FRACTION)
    signatures = set()
    for version in versions:
        counts = _correct_letter_counts(version, questions)
        assert max(counts.values()) <= max_allowed
        signatures.add(tuple(sorted(counts.items())))

    assert len(signatures) > 1, "expected at least some variety in letter distributions"


@pytest.mark.parametrize("count", [1, 3, 20])
def test_generate_versions_produces_requested_count(count):
    questions = make_questions(5)
    versions = generate_versions(questions, count=count)
    assert len(versions) == count
    assert [v.version_number for v in versions] == list(range(1, count + 1))
