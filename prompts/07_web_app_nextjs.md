# Phase 7 — Web app migration (Flutter web → Next.js)

## Objective
Replace the Flutter-web professor dashboard with a **Next.js (TypeScript) web app**,
while leaving the **Flutter mobile app untouched** (Phase 8 stays exactly as specified).
Functional scope does not change from the original Phase 7 spec — only the client
technology for the web dashboard changes. The web app remains the professor's full
control center: auth, quiz creation, version generation, PDF download, results
dashboard, flagged-answer review.

## Why this migration (context, not a decision point)
Web and mobile no longer need to share a rendering target. Mobile keeps Flutter for
camera access and native scanning UX; web moves to Next.js for faster iteration, a
larger component/testing ecosystem, and simpler static/SSR hosting independent of the
mobile release cycle.

## Migration-specific ground rules
- **Mobile is out of scope.** Do not modify `/mobile` in this phase. If `/shared`
  currently holds a Dart package used by both clients, keep only the parts mobile still
  needs; do not delete anything mobile depends on.
- **Backend contract is frozen.** The FastAPI routes and request/response schemas from
  Phases 1–6 do not change. The web app is a pure client of the existing API. If a
  genuine backend gap is discovered, log it in `BLOCKERS.md` and stop to ask — do not
  add or reshape endpoints to suit the new frontend.
- **No LLM calls introduced anywhere.** Section 2 of CLAUDE.md still applies in full.
- All original Phase 7 functional requirements still apply — only the verification
  tooling changes (Playwright/RTL instead of `flutter test`).

## Subtask 7.0 — Decommission old Flutter web + scaffold Next.js
**Steps:**
- Remove the Flutter `/web` project from the repo with `git rm`, in its own commit,
  separate from the commit that adds the new app.
- Scaffold `/web` as a Next.js 15+ project (App Router) with TypeScript.
- Add Tailwind CSS for styling.
- Add `@supabase/supabase-js` and `@supabase/ssr` for server- and client-side auth
  session handling.
- Add a typed API client layer at `/web/lib/api/` wrapping fetch calls to the FastAPI
  backend (hand-written TS types mirroring the Pydantic schemas is sufficient; an
  OpenAPI-generated client is a nice-to-have, not required).
- Add testing tooling: Vitest + React Testing Library for components/units, Playwright
  for e2e (this replaces Flutter's widget/integration tests as the verification layer
  for every DoD item below).
- Add ESLint + Prettier configs and `lint` / `format` / `test` / `build` npm scripts.
- Update the root CI workflow (from Phase 0.3) to run the Next.js jobs (`npm run lint`,
  `npm test`, `npx playwright test`, `npm run build`) in place of the old `flutter
  analyze` / `flutter test` job for `/web`. The mobile CI job is untouched.

**Definition of Done:**
- [ ] `/web` contains no Flutter files or config; the removal and the Next.js scaffold
      are two distinct, clearly labeled commits.
- [ ] `npm run dev` boots the app locally with a working default page.
- [ ] `npm run build` produces a production build with zero errors.
- [ ] `npm run lint` and `npm test` both exit 0 (placeholder tests are fine at this
      point).
- [ ] `/mobile` still builds and its existing test suite still passes, completely
      unmodified.
- [ ] CI config is valid and its Next.js job runs the four commands above successfully.

## Subtask 7.1 — Auth & shell
**Steps:**
- Supabase Auth (email/password) via `@supabase/ssr`, with session handling in
  `middleware.ts` so protected routes are guarded **server-side**, before render — not
  only via a client-side check.
- App shell: top-level layout with navigation (Quizzes, Results, Account) and sign-out.

**Definition of Done:**
- [ ] Sign up, log in, log out all work against a real (test) Supabase project, verified
      by a Playwright e2e test.
- [ ] A request to a protected route with no valid session cookie is redirected
      server-side — verified by a test that hits the route directly (not just by
      confirming a client-side guard exists).

## Subtask 7.2 — Quiz creation flow
**Steps:**
- Page: create quiz (title) → upload Excel (multipart POST to the existing backend
  endpoint) → show parsed questions for confirmation → surface Phase 2's structured
  validation errors mapped to the exact row/reason.
- Page: choose number of versions → trigger generation → show progress/result.

**Definition of Done:**
- [ ] Uploading the Phase 2 "invalid" fixture surfaces every row error clearly in the
      UI, verified by a Playwright test asserting the error text appears for each bad
      row.
- [ ] Successful flow ends with N versions visible and downloadable, verified
      end-to-end against a real (test) backend.

## Subtask 7.3 — Version download screen
**Steps:**
- List generated versions with a download control per version (calls Phase 4's
  endpoint via a signed URL or a proxied route handler).

**Definition of Done:**
- [ ] Clicking download for each version retrieves the correct, distinct PDF (verify
      returned file hashes differ across versions and match backend storage).

## Subtask 7.4 — Results dashboard
**Steps:**
- List submissions per quiz with status (finalized/needs_review), score, timestamp.
- Filter/sort by status.

**Definition of Done:**
- [ ] Dashboard correctly reflects backend state for a seeded set of submissions with
      mixed statuses (verify counts and displayed data match exactly, not just "list
      renders").

## Subtask 7.5 — Flagged-answer review screen
**Steps:**
- For a `needs_review` submission, show each flagged question with (if available) the
  cropped bubble-region image next to the detected result, plus a control for the
  professor to manually select the correct option.
- Calls Phase 6's PATCH endpoint on submit; use client-side refetch/optimistic update
  (React Query, SWR, or manual `router.refresh()`) so status updates without a manual
  page refresh.

**Definition of Done:**
- [ ] Submitting a manual correction updates the UI to reflect the new finalized status
      without a manual page refresh, verified by a Playwright test.
- [ ] A submission with multiple flagged answers requires all of them resolved before
      it leaves the needs_review list (test this boundary explicitly).

## Phase 7 Definition of Done
- [ ] All subtask DoD boxes checked (7.0–7.5).
- [ ] `npm run build`, `npm run lint`, `npm test`, and `npx playwright test` all pass.
- [ ] Old Flutter `/web` is fully removed; no dangling references to it in CI config,
      README, or CLAUDE.md.
- [ ] PROGRESS.md updated, code committed.

## Next
Open `07b_web_migration_testing.md` before continuing to `08_mobile_app.md`.
