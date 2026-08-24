from pathlib import Path

from openpyxl import Workbook

from app.models.question import ParseError, QuestionSchema
from app.services.parsing import _approx_max_chars, _option_width_budget_pt, parse_quiz_excel
from app.services.pdf_gen import load_template

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "excel"
HEADER = ["question_text", "option_a", "option_b", "option_c", "option_d", "correct_option"]


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


def test_long_option_fixture_returns_parse_error_with_exact_row_and_message():
    result = parse_quiz_excel(FIXTURES_DIR / "long_option.xlsx")

    template = load_template()
    max_chars = _approx_max_chars(template, _option_width_budget_pt(template))

    assert isinstance(result, ParseError)
    assert len(result.errors) == 1
    assert result.errors[0].row_number == 2
    assert result.errors[0].messages == [
        f"option_b is too long to print (max ~{max_chars} characters at this column width)"
    ]


def test_option_just_under_width_budget_still_parses(tmp_path):
    """Boundary case tied to the real column geometry, not a guessed char
    count: trims a wide-character string down until it measures just under
    the budget, and confirms that's still accepted."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    template = load_template()
    budget = _option_width_budget_pt(template)
    font_size = template["option_label_font_size"]

    candidate = "W" * 50
    while stringWidth(candidate, "Helvetica", font_size) > budget:
        candidate = candidate[:-1]
    assert candidate, "budget is too small for even a single character - check template config"

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADER)
    sheet.append(["Boundary question", candidate, "Short", "Also short", "Still short", "A"])
    path = tmp_path / "boundary.xlsx"
    workbook.save(path)

    result = parse_quiz_excel(path)

    assert isinstance(result, list)
    assert result[0].options[0] == candidate


def test_multiple_invalid_rows_are_all_reported_together():
    result = parse_quiz_excel(FIXTURES_DIR / "multiple_errors.xlsx")

    assert isinstance(result, ParseError)
    assert [error.row_number for error in result.errors] == [2, 3]
    assert result.errors[0].messages == ["question_text is empty"]
    assert result.errors[1].messages == [
        "option_b is empty",
        "correct_option must be exactly one of A/B/C/D, got 'E'",
    ]
