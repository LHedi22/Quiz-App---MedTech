# Phase 7b — Web migration regression & full-system verification

## Objective
Prove that swapping the web client from Flutter to Next.js introduced **zero
regressions** anywhere in the system — backend, database/RLS, mobile app, and the new
web app itself — before resuming the phase index at Phase 8. This phase exists
specifically because a frontend rewrite is exactly the kind of change that can silently
break auth/session handling, API contracts, or cross-client consistency even when each
piece looks fine in isolation.

This phase does not replace Phase 9 (End-to-end integration testing). It is a
migration-focused gate; Phase 9 later re-validates the whole system again from a clean
slate.

## Subtask 7b.1 — Web app functional regression (re-run, not re-read)
**Steps:**
- Independently re-execute every DoD check from `07_web_app_nextjs.md` (7.0–7.5) as
  live tests, not by re-reading the checklist. Run the full Playwright suite plus the
  Vitest/RTL suite against a real (test) Supabase project and a real (test) FastAPI
  backend — no mocks for this pass.

**Definition of Done:**
- [ ] `npm run build`, `npm run lint`, `npm test`, and `npx playwright test` all pass
      in a single clean run (fresh `node_modules` install, not a cached dev state).
- [ ] Every Phase 7 DoD checkbox is independently re-verified true in this run and
      logged as such in PROGRESS.md (not assumed carried-over from Phase 7).

## Subtask 7b.2 — Auth/session/RLS regression under Next.js SSR
**Steps:**
- Specifically re-test the Phase 1.2 RLS guarantees through the new Next.js
  server-rendered/middleware auth path: user A's session cookie must never expose user
  B's quizzes/questions/versions/submissions/answers via any Next.js route handler or
  server component fetch, not just via direct Supabase client calls.
- Test session expiry/refresh behavior specifically (Next.js SSR cookie handling is a
  common source of silent auth bugs that didn't exist in the Flutter client).

**Definition of Done:**
- [ ] Cross-user RLS test suite (from Subtask 1.2) passes when driven through the
      Next.js app's server routes, not only through direct API/DB calls.
- [ ] A session that expires mid-use redirects to login cleanly (no infinite loop, no
      leaked stale data rendered before redirect) — verified by a test that forces
      token expiry.

## Subtask 7b.3 — Cross-client consistency test
**Steps:**
- Using the Phase 1 seed data (or fresh seeded data), perform a scan through the
  mobile app (or the `/scan` endpoint directly if mobile hardware isn't available) and
  confirm the resulting submission appears correctly in the new Next.js results
  dashboard and flagged-review screen.
- Perform a manual correction via the Next.js PATCH flow and confirm the mobile app's
  batch-summary screen (Phase 8.4) reflects the updated status on next fetch.

**Definition of Done:**
- [ ] A submission created via mobile scan is visible, with correct data, in the
      Next.js dashboard without any manual intervention beyond a normal
      refresh/refetch.
- [ ] A correction made in the Next.js review screen is reflected in mobile's next
      status fetch for that batch.

## Subtask 7b.4 — Full E2E happy-path re-run (Phase 9.1 analog)
**Steps:**
- Re-run the Phase 9.1 happy-path flow (upload Excel → generate 3 versions → download
  each PDF → simulate scanning each version → assert all 3 submissions finalize with
  the mathematically correct scores), but drive every web-facing step through the new
  Next.js app instead of calling backend endpoints directly.

**Definition of Done:**
- [ ] This test passes end-to-end against a real (test/staging) Supabase + backend
      deployment, driven through the Next.js UI, with all 3 submissions finalizing at
      the mathematically correct score.

## Subtask 7b.5 — Full E2E unhappy-path re-run (Phase 9.2 analog)
**Steps:**
- Re-run the Phase 9.2 unhappy-path flow (malformed Excel row, ambiguous bubble scan,
  unreadable QR) driven through the Next.js app where the flow is web-facing (Excel
  upload and its error display), and confirm each failure surfaces correctly in the
  Next.js UI (structured Excel errors mapped to rows, needs_review with the correct
  flagged answer visible and resolvable, distinct QR-failure signal visible wherever
  the web app surfaces submission failures).

**Definition of Done:**
- [ ] All three unhappy paths produce the exact expected system state AND the exact
      expected UI presentation in the Next.js app, verified by assertions against real
      DB rows and real rendered UI text/state — not just "no crash."

## Subtask 7b.6 — CI regression
**Steps:**
- Confirm the CI pipeline updated in Subtask 7.0 is green end-to-end on a fresh push:
  backend job, Next.js job, and mobile job all pass in the same run.

**Definition of Done:**
- [ ] A single CI run on a clean branch shows all three jobs (backend, web/Next.js,
      mobile) passing.
- [ ] No CI step still references Flutter web (`flutter analyze`/`flutter test` for
      `/web`) anywhere in the workflow file.

## Phase 7b Definition of Done
- [ ] All subtask DoD boxes checked (7b.1–7b.6).
- [ ] Any regression found during this phase has been fixed and re-verified, not just
      logged.
- [ ] PROGRESS.md updated with an explicit "migration verified, zero regressions"
      summary line, or a documented list of any known deviations and why they're
      acceptable.
- [ ] Code committed.

## Next
Open `08_mobile_app.md` and continue the loop as originally planned. (Phase 9's
end-to-end tests will still run later and should be treated as a second, independent
confirmation — do not skip Phase 9 because this phase passed.)
