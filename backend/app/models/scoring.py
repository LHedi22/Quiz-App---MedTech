"""Pydantic schemas for the scan/grade pipeline (Phase 6)."""

from __future__ import annotations

from uuid import UUID

from pydantic import AliasChoices, BaseModel, Field, field_validator

# Every question is printed with exactly four options (CLAUDE.md: MCQ only,
# fixed A-D layout). A professor's manual answer edit must be one of these
# or an explicit blank.
VALID_ANSWER_OPTIONS = ("A", "B", "C", "D")


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


class AnswerCorrectionRequest(BaseModel):
    """Body of PATCH /submissions/{id}/answers/{answer_id}: the option the
    professor says the student actually marked. `null` means "left blank".

    `correct_option` is the historical field name (it never meant the answer
    key - always "what the student marked"); accepted as an alias so an
    older client keeps working. The key must be present in the body either
    way - omitting it is a 422, not a silent blank.
    """

    marked_option: str | None = Field(
        validation_alias=AliasChoices("marked_option", "correct_option"),
    )

    @field_validator("marked_option")
    @classmethod
    def _normalize_option(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if normalized == "":
            return None
        if normalized not in VALID_ANSWER_OPTIONS:
            raise ValueError(f"marked_option must be one of {VALID_ANSWER_OPTIONS} or null (blank)")
        return normalized
