"""Pydantic schemas for the scan/grade pipeline (Phase 6)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class QuestionForScoring(BaseModel):
    """Minimal view of a `questions` row needed to grade a detected answer."""

    id: UUID
    order_index: int  # canonical question number, matches answers.question_no
    correct_option: str  # canonical letter, e.g. "A"


class VersionForScoring(BaseModel):
    id: UUID
    quiz_id: UUID
    question_order: list[UUID]  # shuffled order, canonical question ids
    option_order: dict[str, list[int]]  # question_id (str) -> canonical indices in shuffled order


class VersionLookupResult(BaseModel):
    """Subtask 6.1's return shape: a version plus the canonical answer key
    for every question it contains."""

    version: VersionForScoring
    questions_by_id: dict[UUID, QuestionForScoring]


class DetectedAnswer(BaseModel):
    """Raw per-position bubble classification for one row (= one shuffled
    question position) of a scanned page, as produced by running
    `app/ml/omr/classify.py::classify_bubble` over every option in that row."""

    position: int  # 0-based index into version.question_order
    option_labels: list[str]  # "filled" / "empty" / "ambiguous", one per shuffled option index
    option_confidences: list[float]  # same order as option_labels


class ScoredAnswer(BaseModel):
    question_no: int
    question_id: UUID
    detected_option: str | None  # canonical letter, None if unreadable/ambiguous
    confidence: float
    flagged: bool
    correct: bool | None
    score: float | None


class ScoringResult(BaseModel):
    total_score: float | None  # None while any answer is flagged (status != finalized)
    status: str  # "finalized" | "needs_review"
    answers: list[ScoredAnswer]
