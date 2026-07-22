"""Regenerates the .xlsx fixtures documented in /docs/EXCEL_FORMAT.md.

Run with: python tests/fixtures/excel/generate_fixtures.py
The generated files are committed to git, so this only needs to be re-run if the
fixture content itself changes.
"""

from pathlib import Path

from openpyxl import Workbook

FIXTURES_DIR = Path(__file__).parent

HEADER = ["question_text", "option_a", "option_b", "option_c", "option_d", "correct_option"]


def write_workbook(filename: str, rows: list[list[str]]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADER)
    for row in rows:
        sheet.append(row)
    workbook.save(FIXTURES_DIR / filename)


def main() -> None:
    write_workbook(
        "valid.xlsx",
        [
            [
                "What is the powerhouse of the cell?",
                "Nucleus",
                "Mitochondria",
                "Ribosome",
                "Golgi apparatus",
                "B",
            ],
            [
                "Which molecule carries genetic information?",
                "ATP",
                "RNA polymerase",
                "DNA",
                "Glucose",
                "C",
            ],
            ["What is 2 + 2?", "3", "4", "5", "6", "b"],
        ],
    )

    write_workbook(
        "missing_answer.xlsx",
        [
            [
                "What is the powerhouse of the cell?",
                "Nucleus",
                "Mitochondria",
                "Ribosome",
                "Golgi apparatus",
                "B",
            ],
            ["What is the capital of France?", "Paris", "London", "Berlin", "Madrid", ""],
        ],
    )

    write_workbook(
        "duplicate_options.xlsx",
        [
            [
                "What is the powerhouse of the cell?",
                "Nucleus",
                "Mitochondria",
                "Ribosome",
                "Golgi apparatus",
                "B",
            ],
            ["Pick a city", "Paris", "London", "Paris", "Madrid", "A"],
        ],
    )

    # Not one of the 3 required fixtures from Subtask 2.1 -- an extra fixture proving
    # the parser collects errors from *every* bad row, not just the first (Subtask 2.2).
    write_workbook(
        "multiple_errors.xlsx",
        [
            ["", "A1", "A2", "A3", "A4", "A"],
            ["Some question", "X", "", "Y", "Z", "E"],
        ],
    )


if __name__ == "__main__":
    main()
