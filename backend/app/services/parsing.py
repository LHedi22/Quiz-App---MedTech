"""Parses professor-uploaded .xlsx quiz files into QuestionSchema rows.

Column layout and validation rules are documented in /docs/EXCEL_FORMAT.md.
"""

from openpyxl import load_workbook
from reportlab.pdfbase.pdfmetrics import stringWidth

from app.models.question import ParseError, QuestionSchema, RowError
from app.services.pdf_gen import load_template

OPTION_LETTERS = ["A", "B", "C", "D"]

# A printed option must fit within its column before the next option's bubble
# begins, or the two overlap on the page (found via a real end-to-end scan
# that surfaced overlapping option text degrading OMR confidence). Both
# numbers are measured against the same app/config/pdf_template.json that
# pdf_gen.py actually renders with, so this budget can never drift out of
# sync with the real layout.
_SAMPLE_TEXT = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 "


def _option_width_budget_pt(template: dict) -> float:
    # text_start_offset_pt matches pdf_gen.py's _draw_question layout;
    # safety_margin_pt reserves room for the next column's letter label.
    text_start_offset_pt = template["bubble_radius_pt"] + 4
    safety_margin_pt = abs(template["bubble_label_dx_pt"])
    return template["option_spacing_x_pt"] - text_start_offset_pt - safety_margin_pt


def _approx_max_chars(template: dict, budget_pt: float) -> int:
    font_size = template["option_label_font_size"]
    total_width_pt = stringWidth(_SAMPLE_TEXT, "Helvetica", font_size)
    avg_char_width_pt = total_width_pt / len(_SAMPLE_TEXT)
    return int(budget_pt / avg_char_width_pt)


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

    template = load_template()
    option_width_budget_pt = _option_width_budget_pt(template)
    max_chars = _approx_max_chars(template, option_width_budget_pt)
    option_font_size = template["option_label_font_size"]

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
            elif stringWidth(option, "Helvetica", option_font_size) > option_width_budget_pt:
                messages.append(
                    f"option_{letter.lower()} is too long to print "
                    f"(max ~{max_chars} characters at this column width)"
                )

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
