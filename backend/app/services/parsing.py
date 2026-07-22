"""Parses professor-uploaded .xlsx quiz files into QuestionSchema rows.

Column layout and validation rules are documented in /docs/EXCEL_FORMAT.md.
"""

from openpyxl import load_workbook

from app.models.question import ParseError, QuestionSchema, RowError

OPTION_LETTERS = ["A", "B", "C", "D"]


def _normalize_cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_blank_row(row: tuple) -> bool:
    return all(_normalize_cell(cell) == "" for cell in row)


def parse_quiz_excel(file) -> list[QuestionSchema] | ParseError:
    """Parse an uploaded .xlsx file (path or file-like object).

    Returns the full list of QuestionSchema only if every data row is valid.
    If any row is invalid, returns a ParseError covering every faulty row
    (not just the first), so a professor can fix everything in one pass.
    """
    workbook = load_workbook(file, read_only=True, data_only=True)
    sheet = workbook.active

    row_errors: list[RowError] = []
    questions: list[QuestionSchema] = []
    order_index = 0

    for row_number, raw_row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        row = tuple(raw_row[i] if i < len(raw_row) else None for i in range(6))
        if _is_blank_row(row):
            continue

        order_index += 1
        question_text, option_a, option_b, option_c, option_d, correct_option_raw = (
            _normalize_cell(cell) for cell in row
        )
        options = [option_a, option_b, option_c, option_d]

        messages: list[str] = []
        if not question_text:
            messages.append("question_text is empty")

        for letter, option in zip(OPTION_LETTERS, options):
            if not option:
                messages.append(f"option_{letter.lower()} is empty")

        non_empty_options = [option for option in options if option]
        if len(non_empty_options) != len(set(non_empty_options)):
            messages.append("options must be unique within the row (duplicate option text found)")

        correct_option = correct_option_raw.upper()
        if correct_option not in OPTION_LETTERS:
            messages.append(
                f"correct_option must be exactly one of A/B/C/D, got {correct_option_raw!r}"
            )

        if messages:
            row_errors.append(RowError(row_number=row_number, messages=messages))
            continue

        questions.append(
            QuestionSchema(
                text=question_text,
                options=options,
                correct_option=correct_option,
                order_index=order_index,
            )
        )

    if row_errors:
        return ParseError(errors=row_errors)
    return questions
