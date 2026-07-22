from uuid import UUID

from pydantic import BaseModel


class QuestionForShuffle(BaseModel):
    """Minimal view of a `questions` row needed to shuffle it into a version."""

    id: UUID
    options: list[str]
    correct_option: str  # canonical letter, e.g. "A"


class ShuffledVersion(BaseModel):
    """A single generated version, shaped to match the `versions` table columns."""

    version_number: int
    question_order: list[UUID]
    option_order: dict[str, list[int]]  # question_id (str) -> canonical indices in shuffled order


class VersionCreateRequest(BaseModel):
    count: int
