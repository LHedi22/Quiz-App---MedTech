# Phase 3 — Version generation (shuffle engine)

## Objective
Given a quiz's questions, generate N versions, each with an independently shuffled
question order and, within each question, an independently shuffled option order —
plus a constraint pass so the correct answer letter isn't obviously clustered.

## Subtask 3.1 — Core shuffle algorithm
**Steps:**
- `app/services/shuffler.py`: `generate_version(questions, version_number, seed) -> Version`
- Use Fisher-Yates (or Python's `random.shuffle` with an explicit seeded `Random` instance
  for reproducibility) for question order.
- For each question, independently shuffle its options, and track where the correct
  option landed (canonical → new letter mapping).
- Store the result as `question_order` (list of canonical question IDs in new order) and
  `option_order` (dict of question_id → list of canonical option indices in new order),
  matching the schema in CLAUDE.md Section 4.

**Definition of Done:**
- [ ] For a 10-question quiz, generating 5 versions produces 5 distinct question orders
      (assert no two versions have identical `question_order`, unless N is so large
      collisions are mathematically expected — cap realistic N in tests, e.g. ≤20).
- [ ] For every version, every question's option order is a valid permutation of the
      canonical options (same set, different order) — verified programmatically, not by eye.
- [ ] The correct answer can always be traced back correctly: for a known input, manually
      verify at least 2 versions end-to-end that the stored mapping correctly identifies
      the shuffled position of the true correct answer.

## Subtask 3.2 — Anti-clustering constraint
**Steps:**
- Add a pass that re-rolls a version's option shuffle if the correct-answer letter
  distribution across a single version's questions is too skewed (e.g. more than 50% of
  correct answers landing on the same letter) or if it repeats the exact same
  distribution across versions.
- Make the threshold configurable (constant at top of file), not hardcoded inline.

**Definition of Done:**
- [ ] Test with a 12-question quiz: generate 20 versions, assert no version has more than
      the configured threshold of correct answers on one letter.
- [ ] Test proves the re-roll doesn't infinite-loop (max attempts + fallback behavior
      defined and tested).

## Subtask 3.3 — API endpoint + storage
**Steps:**
- `POST /quizzes/{quiz_id}/versions` accepting `{count: N}`, generating N versions via
  the shuffler, and inserting rows into `versions`.
- Reject (400) if `count < 1` or the quiz has zero questions.
- Ensure versions, once created, are immutable (no update endpoint for `question_order`/
  `option_order` — only creation and read).

**Definition of Done:**
- [ ] Integration test: requesting 5 versions for a valid quiz creates exactly 5 rows in
      `versions`, each passing the Subtask 3.1/3.2 checks.
- [ ] Integration test: requesting versions for a quiz with 0 questions returns 400.
- [ ] Confirm there is no code path that can update an existing version's shuffle data.

## Phase 3 Definition of Done
- [ ] All subtask DoD boxes checked.
- [ ] PROGRESS.md updated, code committed.

## Next
Open `04_pdf_qr_generation.md`.