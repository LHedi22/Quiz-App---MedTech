# Phase 2 — Excel upload, validation, parsing

## Objective
A professor can upload an `.xlsx` file of MCQ questions + options + correct answers, and
the system parses it into `quizzes` + `questions` rows, rejecting malformed input with
clear error messages.

## Subtask 2.1 — Define the expected Excel format
**Steps:**
- Decide and document the exact column layout, e.g.:
  `question_text | option_a | option_b | option_c | option_d | correct_option`
- Write this spec into `/docs/EXCEL_FORMAT.md` with a real example table.
- Create 3 sample `.xlsx` fixtures: one valid, one with a missing correct answer, one with
  duplicate options in the same row.

**Definition of Done:**
- [ ] `/docs/EXCEL_FORMAT.md` exists with the column spec and an example.
- [ ] 3 fixture files exist under `/backend/tests/fixtures/excel/`.

## Subtask 2.2 — Parsing service
**Steps:**
- `app/services/parsing.py`: function `parse_quiz_excel(file) -> list[QuestionSchema] | ParseError`.
- Use `openpyxl`/`pandas` to read rows, validate: no empty question text, exactly one
  correct option marked, options are non-empty and non-duplicate within a row.
- On any row failure, collect ALL row errors (not just the first) and return them together
  with row numbers, so a professor can fix everything in one pass.

**Definition of Done:**
- [ ] Valid fixture parses into the correct number of `QuestionSchema` objects with correct
      field values (assert exact content, not just count).
- [ ] Invalid fixtures return a `ParseError` listing every faulty row with a human-readable
      reason, verified by exact string/row-number assertions in tests.

## Subtask 2.3 — Upload endpoint
**Steps:**
- `POST /quizzes/{quiz_id}/upload` (or `/quizzes` create-with-upload) accepting a file,
  calling the parsing service, and on success inserting rows into `questions` linked to
  the quiz.
- On parse failure, return HTTP 422 with the structured error list, not a generic 500.

**Definition of Done:**
- [ ] Integration test: valid file upload → 201/200 response → correct rows present in DB.
- [ ] Integration test: invalid file upload → 422 response with structured errors → no
      partial rows written to DB (all-or-nothing, verify via rollback).

## Phase 2 Definition of Done
- [ ] All subtask DoD boxes checked.
- [ ] PROGRESS.md updated, code committed.

## Next
Open `03_version_generation.md`.