from pathlib import Path

from app.models.question import ParseError, QuestionSchema
from app.services.parsing import parse_quiz_excel

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "excel"


def test_valid_fixture_parses_into_exact_question_schemas():
    result = parse_quiz_excel(FIXTURES_DIR / "valid.xlsx")

    assert isinstance(result, list)
    assert len(result) == 3
    assert result == [
        QuestionSchema(
            text="What is the powerhouse of the cell?",
            options=["Nucleus", "Mitochondria", "Ribosome", "Golgi apparatus"],
            correct_option="B",
            order_index=1,
        ),
        QuestionSchema(
            text="Which molecule carries genetic information?",
            options=["ATP", "RNA polymerase", "DNA", "Glucose"],
            correct_option="C",
            order_index=2,
        ),
        QuestionSchema(
            text="What is 2 + 2?",
            options=["3", "4", "5", "6"],
            correct_option="B",  # lowercase "b" in the fixture normalizes to "B"
            order_index=3,
        ),
    ]


def test_missing_answer_fixture_returns_parse_error_with_exact_row_and_message():
    result = parse_quiz_excel(FIXTURES_DIR / "missing_answer.xlsx")

    assert isinstance(result, ParseError)
    assert len(result.errors) == 1
    assert result.errors[0].row_number == 3
    assert result.errors[0].messages == ["correct_option must be exactly one of A/B/C/D, got ''"]


def test_duplicate_options_fixture_returns_parse_error_with_exact_row_and_message():
    result = parse_quiz_excel(FIXTURES_DIR / "duplicate_options.xlsx")

    assert isinstance(result, ParseError)
    assert len(result.errors) == 1
    assert result.errors[0].row_number == 3
    assert result.errors[0].messages == [
        "options must be unique within the row (duplicate option text found)"
    ]


def test_multiple_invalid_rows_are_all_reported_together():
    result = parse_quiz_excel(FIXTURES_DIR / "multiple_errors.xlsx")

    assert isinstance(result, ParseError)
    assert [error.row_number for error in result.errors] == [2, 3]
    assert result.errors[0].messages == ["question_text is empty"]
    assert result.errors[1].messages == [
        "option_b is empty",
        "correct_option must be exactly one of A/B/C/D, got 'E'",
    ]
