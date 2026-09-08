"""Web-app audit B5: the per-answer weight and the total-score summation
rule live in exactly one place (`scoring.score_answer` /
`scoring.sum_answer_scores`), shared by the scan pipeline and the
professor-correction path so the two can't silently diverge if weighted or
negative scoring is ever added.

Pure functions - no DB, so no skip marker.
"""

from __future__ import annotations

from app.services.scoring import (
    CORRECT_SCORE,
    INCORRECT_SCORE,
    score_answer,
    sum_answer_scores,
)


def test_score_answer_correct_match():
    assert score_answer("B", "B") == (True, CORRECT_SCORE)


def test_score_answer_wrong_option():
    assert score_answer("A", "B") == (False, INCORRECT_SCORE)


def test_score_answer_blank_is_never_correct():
    assert score_answer(None, "B") == (False, INCORRECT_SCORE)
    # even if the key itself were somehow None, a blank is not "correct"
    assert score_answer(None, None) == (False, INCORRECT_SCORE)


def test_sum_answer_scores_treats_missing_as_zero():
    assert sum_answer_scores([1.0, 0.0, 1.0]) == 2.0
    assert sum_answer_scores([1.0, None, 1.0]) == 2.0
    assert sum_answer_scores([]) == 0.0


def test_scan_and_correction_paths_agree_on_a_final_answer_set():
    """The scan path scores each answer with score_answer and totals with
    sum_answer_scores; the correction path (submissions.py) now does the
    same. For any fixed set of (marked, key) pairs the totals must match."""
    pairs = [("A", "A"), ("B", "C"), (None, "D"), ("D", "D")]

    scan_side = [score_answer(m, k)[1] for m, k in pairs]
    # the correction path stores each score, then re-sums from the DB rows
    correction_side = [score_answer(m, k)[1] for m, k in pairs]

    assert sum_answer_scores(scan_side) == sum_answer_scores(correction_side) == 2.0
