from pydantic import BaseModel


class QuestionSchema(BaseModel):
    text: str
    options: list[str]
    correct_option: str
    order_index: int


class RowError(BaseModel):
    row_number: int
    messages: list[str]


class ParseError(BaseModel):
    errors: list[RowError]
