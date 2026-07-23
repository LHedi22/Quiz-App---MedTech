from pydantic import BaseModel, Field


class QuizCreateRequest(BaseModel):
    title: str = Field(min_length=1)
