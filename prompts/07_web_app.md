# Phase 7 — Web app (Flutter web)

## Objective
Build the professor's full control-center UI: auth, quiz creation, version generation,
PDF download, results dashboard, flagged-answer review.

## Subtask 7.1 — Auth & shell
**Steps:**
- Supabase Auth integration (email/password at minimum).
- App shell with navigation: Quizzes, Results, (Account).

**Definition of Done:**
- [ ] Sign up, log in, log out all work against a real Supabase project, verified by a
      widget/integration test hitting a test Supabase instance.
- [ ] Unauthenticated users are redirected away from protected routes (test this
      explicitly, don't just assume the route guard works).

## Subtask 7.2 — Quiz creation flow
**Steps:**
- Screen: create quiz (title) → upload Excel → show parsed questions for confirmation →
  show any validation errors from Phase 2's structured error list, mapped to the exact
  row/reason.
- Screen: choose number of versions → trigger generation → show progress/result.

**Definition of Done:**
- [ ] Uploading the Phase 2 "invalid" fixture surfaces every row error clearly in the UI,
      verified by a widget test asserting the error text appears for each bad row.
- [ ] Successful flow ends with N versions visible and downloadable, verified end-to-end
      against a real (test) backend.

## Subtask 7.3 — Version download screen
**Steps:**
- List generated versions with a download button per version (calls Phase 4's endpoint).

**Definition of Done:**
- [ ] Clicking download for each version retrieves the correct, distinct PDF (verify by
      checking returned file hashes differ across versions and match backend storage).

## Subtask 7.4 — Results dashboard
**Steps:**
- List submissions per quiz with status (finalized/needs_review), score, timestamp.
- Filter/sort by status.

**Definition of Done:**
- [ ] Dashboard correctly reflects backend state for a seeded set of submissions with mixed
      statuses (verify counts and displayed data match exactly, not just "list renders").

## Subtask 7.5 — Flagged-answer review screen
**Steps:**
- For a `needs_review` submission, show each flagged question with (if available) the
  cropped bubble-region image next to the detected result, and a control for the professor
  to manually select the correct option.
- Calls Phase 6's PATCH endpoint on submit.

**Definition of Done:**
- [ ] Submitting a manual correction updates the UI to reflect the new finalized status
      without requiring a manual page refresh (verify reactive state update).
- [ ] A submission with multiple flagged answers requires all of them resolved before it
      leaves the needs_review list (test this boundary explicitly).

## Phase 7 Definition of Done
- [ ] All subtask DoD boxes checked.
- [ ] `flutter test` passes fully for the web app.
- [ ] PROGRESS.md updated, code committed.

## Next
Open `08_mobile_app.md`.