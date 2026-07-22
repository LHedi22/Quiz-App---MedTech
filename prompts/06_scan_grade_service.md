# Phase 6 — Scan & grade service

## Objective
Wire together Phase 5's components into the full pipeline: capture image → decode QR →
fetch version mapping → align → detect bubbles → translate to canonical answers → score
→ confidence gate → finalize or flag for review.

## Subtask 6.1 — Version lookup
**Steps:**
- `app/services/scoring.py`: given a decoded `qr_id`, fetch the corresponding `versions`
  row (and its parent quiz's `questions` for the master answer key).
- Handle "qr_id not found" as a distinct, clearly-surfaced error (could mean a corrupted
  scan or a QR from a different, unrelated quiz).

**Definition of Done:**
- [ ] Test with a valid seeded `qr_id` returns the correct version + question data.
- [ ] Test with a nonexistent `qr_id` returns a clear "not found" result, not an exception
      leak or silent None.

## Subtask 6.2 — Translate & score
**Steps:**
- Given detected bubble results (per position) and the version's `question_order` /
  `option_order` mapping, translate each detected position back to
  (canonical_question_id, canonical_option_letter), then compare against
  `questions.correct_option`.
- Compute `total_score` and per-answer `correct`/`score` values.

**Definition of Done:**
- [ ] Using the Phase 1 seed data (known version mapping + a constructed set of "detected"
      answers), the computed score exactly matches a hand-calculated expected score for at
      least 3 different constructed answer sets (all-correct, all-wrong, mixed).
- [ ] Confirm the translation logic correctly un-shuffles even when question order AND
      option order are both non-identity permutations (i.e. test the hardest case, not
      just a trivial one where order happens to match canonical).

## Subtask 6.3 — Confidence gate
**Steps:**
- Define and implement the concrete rules from CLAUDE.md Section 2.5: QR unreadable → whole
  submission flagged; per-question — zero bubbles filled, multiple bubbles filled, or
  classifier confidence below a configured threshold → that answer is `flagged=true` and
  excluded from auto-finalization.
- A submission is `finalized` only if zero of its answers are flagged; otherwise its
  status is `needs_review`.

**Definition of Done:**
- [ ] Test: an all-high-confidence, all-single-mark answer set produces
      `status = finalized`.
- [ ] Test: an answer set containing one ambiguous/multi-mark case produces
      `status = needs_review`, and exactly that answer (not others) is flagged.
- [ ] Test: a submission with an unreadable QR never reaches scoring logic at all, and is
      surfaced as a distinct failure mode (not silently treated as "needs review").

## Subtask 6.4 — Scan endpoint + professor review endpoint
**Steps:**
- `POST /scan` accepting an image (or image + optional student_id), running the full
  pipeline, returning the submission result (finalized or needs_review with flagged
  question numbers).
- `GET /submissions?status=needs_review` for the web dashboard to list items needing
  professor attention.
- `PATCH /submissions/{id}/answers/{answer_id}` for a professor to manually set the
  correct detected option on a flagged answer, which then recalculates `total_score` and,
  if all answers are now resolved, flips status to `finalized`.

**Definition of Done:**
- [ ] End-to-end integration test: POST a real (or realistic synthetic) scanned image
      through `/scan` and confirm the final DB state (submission + answers) is fully
      correct.
- [ ] Integration test: a professor's manual correction via PATCH correctly updates score
      and status.

## Phase 6 Definition of Done
- [ ] All subtask DoD boxes checked.
- [ ] PROGRESS.md updated, code committed.

## Next
Open `07_web_app.md`.