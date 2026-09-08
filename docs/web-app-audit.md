# Web app audit — 2026-09-03

Full pass over `/web` (every route, `lib/api`, `lib/scan`, `lib/supabase`, `proxy.ts`,
components) plus the backend endpoints the web client calls
(`backend/app/routers/{quizzes,versions,scan}.py`, `backend/app/services/submissions.py`,
`backend/app/main.py`).

Baseline at time of audit: `npx tsc --noEmit` clean, `npm run lint` clean,
`npx vitest run` = 20/20 passing.

Each item is written to be turned into its own fix plan. Severity: **P1** = data
exposure or a broken core flow in a plausible config; **P2** = wrong behavior or a
dead-end in a real scenario; **P3** = UX / polish / latent coupling.

---

## P1 — Security / data isolation

### A1. `GET /submissions` has no auth and no ownership scoping
- **Severity:** P1  **Confidence:** high
- **Location:** `backend/app/routers/scan.py:211-215` (`list_submissions`)
- **Symptom:** The endpoint is registered with no `Depends(get_current_user)` and the
  query (`submissions_service.list_submissions_by_status`, `submissions.py:190-197`)
  filters only by `status`, never by owner. Any caller — unauthenticated — can retrieve
  every professor's submissions for a given status: `id`, `student_id`, `student_name`,
  `name_confidence`, `total_score`, `status`, `created_at`, across all quizzes and all
  users.
- **Root cause:** Route predates the API-layer ownership convention documented in
  `quizzes.py` / `app/db.py`; never retrofitted. Matches the known failure pattern in the
  `backend_ownership_check_pattern` memory ("no RLS safety net; grep for missing
  `Depends(get_current_user)`").
- **Scenario:** `curl https://<backend>/submissions?status=finalized` returns other
  professors' student rows.
- **Web impact:** The web client does **not** call this route (it uses
  `GET /quizzes/{id}/submissions`, which is correctly scoped). So the fix is unlikely to
  break the web app — but confirm no other client depends on it before changing the
  contract (CLAUDE.md Section 2 rule 7).
- **Suggested fix:** Add `user: AuthUser = Depends(get_current_user)` + `ensure_user_row`,
  and scope the query to submissions whose `versions.quiz_id` joins to a quiz with
  `owner_id = user.id`. If the route has no remaining caller, consider deleting it
  instead.
- **Tests to add:** backend test asserting 401 without a token, and that professor A
  cannot see professor B's submission via this route.

### A2. `POST /scan` is fully unauthenticated; web no longer needs it that way
- **Severity:** P1 (defense in depth)  **Confidence:** high
- **Location:** `backend/app/routers/scan.py:93-96`; web callers
  `web/lib/scan/scanApi.ts:46-57`, `web/app/(app)/scan/page.tsx:23-32`
- **Symptom:** `scan_submission(file, student_id=None, capture_id=None)` has no auth
  dependency. `student_id` and `capture_id` arrive as unvalidated query-string scalars.
  Anyone who can reach the backend and render a valid version QR can create submissions
  (and pollute a professor's results dashboard) anonymously.
- **Root cause:** Deliberate historical decision for the Flutter offline path (mobile had
  no session at scan time). Phase 7c made the web `/scan` screen live behind the
  authenticated `(app)` route group (`proxy.ts` redirects anonymous users to `/login`),
  so on the web the "anonymous professor" path is now unreachable dead code — and the
  code comments in `scanApi.ts` / `scan/page.tsx` that describe it as a supported mode
  are misleading.
- **Scenario:** Scripted POST of arbitrary images to `/scan` with a guessed/printed QR.
- **Suggested fix (needs a product decision — log in BLOCKERS if unsure):** Either
  (a) require auth on `/scan` and give the Flutter app a service token / deferred-auth
  story, or (b) keep it open but document why explicitly and add rate limiting + a
  per-version submission cap. At minimum: on the web, make `tryGetAccessToken` failure a
  hard error (don't submit unauthenticated) and correct the comments.
- **Tests to add:** whichever direction is chosen, a test pinning the intended auth
  behavior of `/scan`.

### A3. CORS is silently all-or-nothing on a single env var
- **Severity:** P1 (deploy fragility)  **Confidence:** medium
- **Location:** `backend/app/main.py:16-24`
- **Symptom:** Browser calls from the deployed web app only work if `ALLOWED_ORIGINS`
  contains the exact Vercel origin. If unset or wrong, **every** cross-origin call from
  the web app fails preflight: quiz create, Excel upload, version list, PDF URL,
  submission list, submission detail, answer/name PATCH, `POST /scan`, and the
  `/health` reachability ping. The `/health` failure specifically makes `/scan` render a
  permanent "no connection — scanning unavailable" banner
  (`web/lib/scan/useReachability.ts:27-32` treats a rejected fetch as offline).
- **Root cause:** No fallback, no boot-time warning when `ALLOWED_ORIGINS` is empty in a
  non-local `ENV`. Comment still refers to "the Flutter web client".
- **Suggested fix:** Log a warning at startup if `ENV` is `staging`/`production` and
  `_extra_origins` is empty. Update the comment to Next.js. Consider deriving the origin
  from a known env var (e.g. `WEB_ORIGIN`) already set for other reasons. Add
  `max_age=600` to cut preflight chatter.
- **Tests to add:** a startup/config test asserting the warning fires; an integration
  check that `/health` responds with `Access-Control-Allow-Origin` for a configured
  origin.

### A4. No HTTP security headers on the web app
- **Severity:** P1 (low effort, handles student PII)  **Confidence:** high
- **Location:** `web/next.config.ts` (empty scaffold)
- **Symptom:** No `Content-Security-Policy`, `Strict-Transport-Security`,
  `X-Frame-Options` / `frame-ancestors`, `X-Content-Type-Options`, `Referrer-Policy`.
  The app is clickjackable and has no CSP despite showing student names and scores.
- **Suggested fix:** Add a `headers()` block in `next.config.ts` (or a response-header
  pass in `proxy.ts`). Start with `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, HSTS, and a report-only
  CSP tightened over time (note: `next/font` inlines styles, Supabase needs `connect-src`
  to its URL, the backend needs `connect-src` too).
- **Tests to add:** an e2e assertion that key headers are present on a page response.

---

## P2 — Correctness / broken flows

### B1. `Promise.all` over PDF-URL fetches fails the whole versions page on one bad URL
- **Severity:** P2  **Confidence:** high
- **Location:** `web/app/(app)/quizzes/[id]/page.tsx:25-37` (`fetchVersionsAndPdfUrls`),
  used by both the mount `useEffect` (`:45-60`) and `loadVersions` (`:39-43`)
- **Symptom:** If any single `getVersionPdfUrl(version.id)` rejects (storage hiccup,
  signed-URL error, one version failed to render), `Promise.all` rejects → the mount
  effect shows "Could not load versions." even though the version list itself loaded
  fine and most PDFs are available. After `handleGenerate` succeeds, `loadVersions()` can
  reject the same way and surface "Could not generate versions…" even though generation
  worked.
- **Root cause:** All-or-nothing aggregation; version list and per-version PDF URL are
  coupled into one throw.
- **Suggested fix:** Set `versions` from the list immediately; fetch PDF URLs with
  `Promise.allSettled` and populate `pdfUrls` per success. Render "Preparing…" /
  "PDF unavailable — retry" per row (`:113-125` already has a "Preparing…" branch to
  extend). Separate the "generation failed" error from the "reload failed" error in
  `handleGenerate` (`:62-75`).
- **Tests to add:** component/e2e test where one PDF URL 500s and the list still renders
  with a per-row error.

### B2. `Promise.all` over `getSubmission` fails the whole scan-review list on one bad id
- **Severity:** P2  **Confidence:** high
- **Location:** `web/app/(app)/scan/review/page.tsx:33-47`
- **Symptom:** `Promise.all(ids.map((id) => getSubmission(id, token)))` — one id that
  404s (submission deleted, or a transient error) fails the entire page with "Could not
  load this session's flagged submissions", losing access to all the others.
- **Suggested fix:** `Promise.allSettled`; render the ones that resolved, show a small
  "N submissions could not be loaded" note for the rest.
- **Tests to add:** test with a mix of good and 404 ids.

### B3. Capture button re-enables before the frame finishes encoding → duplicate submission
- **Severity:** P2  **Confidence:** medium
- **Location:** `web/app/(app)/scan/page.tsx:128-165`
- **Symptom:** `setCapturing(false)` runs in the synchronous `finally` (`:162-164`), but
  `canvas.toBlob(...)` → `submit(blob)` (`:155-161`) is asynchronous. Between `toBlob`
  being invoked and its callback firing, `capturing` is already `false` and the button is
  re-enabled. A fast second tap captures a *new* frame and calls `submit()` again; each
  `submit()` mints a fresh `crypto.randomUUID()` capture_id
  (`web/lib/scan/useScanQueue.ts:69`), so the backend sees two distinct captures and
  creates two submissions (idempotency only dedupes *retries of the same* capture_id).
- **Root cause:** `capturing` guard released too early; it should stay set until the blob
  is handed to the queue (or the retake reason is shown).
- **Suggested fix:** Move the `setCapturing(false)` for the success path into the
  `toBlob` callback; keep it in `finally` only for the early-return (retake / low-res /
  no-ctx) paths. Or gate on `capturing` inside the `toBlob` callback.
- **Tests to add:** unit test on the capture handler simulating a double invoke;
  assert exactly one `submit`.

### B4. `useReachability` treats any resolved response (incl. 5xx) as "online"
- **Severity:** P2  **Confidence:** high
- **Location:** `web/lib/scan/useReachability.ts:19-33`
- **Symptom:** `await fetch(pingUrl, ...)` with no `response.ok` check → a backend that is
  reachable but erroring (`500`/`502`/`503`, cold-start failure) is reported "online",
  capture is enabled, and every `POST /scan` then fails into the "not submitted — retry"
  state.
- **Suggested fix:** Treat `!response.ok && response.status >= 500` as offline (or
  require `response.ok`). Keep 4xx as "online" (the health route should be 200 anyway).
- **Tests to add:** extend `tests/lib/scan/useReachability.test.ts` with a 503 mock.

### B5. `apply_manual_correction` re-hardcodes the per-question score; two copies of the total-score rule
- **Severity:** P2 (latent)  **Confidence:** high
- **Location:** `backend/app/services/submissions.py:305-306` and `:242-250`
  (`_recompute_submission_status`) vs `backend/app/services/scoring.py:70-73`
  (`_total_score`) and `:115-118`
- **Symptom:** `score = 1.0 if correct else 0.0` in `apply_manual_correction` duplicates
  the scoring weight that lives in `scoring.translate_and_score`. `_recompute_submission_status`
  independently re-sums `answers.score` with `(r[0] or 0.0)` NULL handling, while
  `_total_score` uses `if a.score is not None`. Today every question is worth `1.0`, so
  results agree — but if weighted/negative scoring is ever added to `translate_and_score`,
  a professor's manual edit silently rescales that answer to 1.0/0.0 and the totals
  diverge between the scan path and the correction path.
- **Suggested fix:** Extract a single `score_answer(marked_option, key_option) -> float`
  and a single `sum_answer_scores(...)` helper, used by both the scan pipeline and the
  correction service. No behavior change now; removes the divergence risk.
- **Tests to add:** a test asserting scan-path total and correction-path total match for
  the same final answer set.

### B6. Client-side session expiry dead-ends instead of redirecting to login
- **Severity:** P2  **Confidence:** high
- **Location:** `web/lib/supabase/client.ts:12-21` (`getAccessToken` throws a bare
  `Error("no active session")`); catchers in
  `web/app/(app)/results/[id]/page.tsx:26-38`,
  `web/app/(app)/submissions/[id]/page.tsx:53-63`,
  `web/app/(app)/quizzes/[id]/page.tsx:45-60`,
  `web/app/(app)/scan/review/page.tsx:31-47`,
  `web/app/(app)/quizzes/new/page.tsx`, `web/app/(app)/quizzes/[id]` generate handler
- **Symptom:** The `session-expiry.spec.ts` case only covers a *navigation* (where
  `proxy.ts` redirects cleanly). If the access token expires while the professor sits on
  a client-rendered page and an in-page fetch fires (filter change, save, effect
  refetch), `getAccessToken()` throws and every catch turns it into a generic
  "Could not load…" / "Could not save…" message with no way forward — the user is stuck
  until they manually reload.
- **Root cause:** No shared handling that distinguishes "auth gone" from "request
  failed".
- **Suggested fix:** In `getAccessToken`, attempt `supabase.auth.getUser()` /
  `refreshSession()` first; if there is genuinely no session, `window.location.assign('/login')`
  (or throw a typed `AuthExpiredError` that a shared wrapper catches and redirects on).
  Apply consistently across the client pages and the `ApiError` 401 path in
  `web/lib/api/client.ts:63-72`.
- **Tests to add:** e2e that clears cookies while on `/results/[id]` then triggers a
  refetch, expects a redirect to `/login`.

### B7. Signup with email confirmation enabled silently bounces to `/login`
- **Severity:** P2  **Confidence:** medium (depends on Supabase project setting)
- **Location:** `web/app/signup/actions.ts:6-19`
- **Symptom:** When the Supabase project requires email confirmation, `signUp` returns
  `{ error: null }` with **no session**. The action unconditionally
  `redirect("/quizzes")`; `proxy.ts` sees no user and redirects to `/login`. The
  professor gets no "check your email" message and thinks signup failed.
- **Root cause:** Action assumes `signUp` always establishes a session.
- **Related:** `live_deployment_2026-08-15` memory notes hosted-Auth email
  rate-limit/domain-validation gotchas — confirmation is plausibly on in prod.
- **Suggested fix:** Inspect the `signUp` response; if `data.session` is null and
  `data.user` exists, redirect to a `/signup?pending=1` state (or a dedicated page) that
  says "confirm your email". Also handle the "user already registered" case explicitly.
- **Tests to add:** unit test of the action with a mocked no-session `signUp` response.

### B8. No `error.tsx` / `not-found.tsx` / `loading.tsx` anywhere in `/web`
- **Severity:** P2  **Confidence:** high
- **Location:** whole `web/app` tree; acute in the server components
  `web/app/(app)/quizzes/page.tsx:5-11` and `web/app/(app)/results/page.tsx:5-11`
- **Symptom:** `listQuizzes(session.access_token)` is awaited in a server component with
  no try/catch. A backend 500 / timeout / expired-unrefreshed token throws → Next's raw
  default error page (or a blank segment in prod). No route-level recovery UI anywhere.
- **Suggested fix:** Add `app/(app)/error.tsx` (client, with a retry button) and
  `app/(app)/loading.tsx`; wrap the server-component fetches in try/catch that renders a
  friendly inline error; add a root `app/not-found.tsx`.
- **Tests to add:** e2e with the backend stubbed to 500, assert the error boundary
  renders and "retry" re-fetches.

### B9. `request()` in the API client has no timeout / abort
- **Severity:** P2  **Confidence:** high
- **Location:** `web/lib/api/client.ts:50-75`
- **Symptom:** `fetch` with no `AbortSignal`. A hung backend hangs the awaiting server
  component (and holds the Vercel/Cloud Run request open) until an upstream timeout.
- **Suggested fix:** `AbortSignal.timeout(15000)` (or a config constant) on every
  request; map the abort to a typed `ApiTimeoutError` surfaced like other `ApiError`s.
- **Tests to add:** unit test with a never-resolving fetch mock asserting the timeout
  rejection.

### B10. `PUBLIC_ROUTES` matched with `startsWith`
- **Severity:** P2 (latent)  **Confidence:** high
- **Location:** `web/lib/supabase/middleware.ts:4,35-37`
- **Symptom:** `PUBLIC_ROUTES.some((r) => pathname.startsWith(r))` — any future path
  beginning `/login…` or `/signup…` (e.g. `/login-help`, `/signup/pending` if added as a
  sibling) becomes unauthenticated by accident.
- **Suggested fix:** Match exactly: `pathname === r || pathname.startsWith(r + "/")`, and
  keep the confirmation/pending page (B7) deliberately inside that set if needed.
- **Tests to add:** unit test of the route predicate.

---

## P3 — UX / polish / minor

### C1. Scores shown with no denominator and no rounding
- **Severity:** P3 (high visibility)  **Confidence:** high
- **Location:** `web/app/(app)/results/[id]/page.tsx:124-126, 165-169`;
  `web/app/(app)/submissions/[id]/page.tsx:131-135`
- **Symptom:** `total_score` is rendered raw. It is "count of correct answers" (each
  question = `1.0`, `scoring.py:118`) with no "/ N" and no percentage. A professor sees
  "Score: 7" with no idea of the max; any future fractional scoring would render
  "7.0000001".
- **Suggested fix:** Show `score / answers.length` and/or a percentage. The submission
  detail page already has `submission.answers.length`; the dashboard summary rows need
  the question count — either add it to `SubmissionSummary` from the backend, or fetch
  the quiz's question count once for the page.
- **Tests to add:** component test asserting "7 / 10" style rendering.

### C2. Version-count field: cleared input → 0 → wrong error message; no upper bound
- **Severity:** P3  **Confidence:** high
- **Location:** `web/app/(app)/quizzes/[id]/page.tsx:86-100`, `:62-75`
- **Symptom:** `onChange={(e) => setCount(Number(e.target.value))}` — clearing the field
  yields `Number("") === 0`. Submitting posts `count: 0` → backend
  `versions.py:31-32` returns 400 "count must be at least 1" → caught by the generic
  `catch` → shows "Could not generate versions. Does this quiz have any questions?"
  (misleading). No max — a professor can request thousands of versions (each triggers a
  shuffle + row insert, and later a PDF render).
- **Suggested fix:** Guard `count >= 1` client-side and disable submit otherwise; clamp
  to a sane max (e.g. 100) with an inline message; surface the backend's actual 400
  `detail` instead of the generic string.
- **Tests to add:** component test for empty input and for count above the cap.

### C3. Results dashboard does not revalidate after a review edit
- **Severity:** P3  **Confidence:** high
- **Location:** `web/app/(app)/results/[id]/page.tsx:26-38` (fetch once on mount);
  `web/app/(app)/submissions/[id]/page.tsx:328-333` ("Back to results" `<Link>`)
- **Symptom:** Edit a submission's answers/name/status on the detail page, click "Back to
  results" → the list still shows the pre-edit status and score (client cache, no
  refetch, `<Link>` back-navigation doesn't remount).
- **Suggested fix:** Refetch on window focus / route focus, or move the list to
  SWR/React Query (the stack in CLAUDE.md Section 3) with revalidation, or pass a
  `?refresh` signal back from the detail page.
- **Tests to add:** e2e: edit on detail, navigate back, assert updated row.

### C4. "Pending" is a selectable status filter that can never match
- **Severity:** P3  **Confidence:** high
- **Location:** `web/app/(app)/results/[id]/page.tsx:66-71` (`<option value="pending">`)
- **Symptom:** `create_submission` (`submissions.py:70-71`) only ever writes
  `needs_review` or `finalized`; the schema default `pending` is never persisted by any
  code path. The filter option always yields the empty state. `SubmissionStatus` /
  `StatusBadge` also carry a `pending` case that is dead in practice.
- **Suggested fix:** Remove the `pending` filter option (and optionally the type/badge
  case), or document why it's retained. Confirm no backend path sets `pending` first.
- **Tests to add:** n/a (removal); or a backend test proving `pending` is unreachable.

### C5. `/scan/review?ids=` can exceed practical URL length
- **Severity:** P3  **Confidence:** medium
- **Location:** `web/app/(app)/scan/page.tsx:260-268` (builds `?ids=` from
  `needsReviewSubmissionIds`), consumed at `web/app/(app)/scan/review/page.tsx:22-26`
- **Symptom:** ~55 UUIDs (~2 KB) is the practical ceiling for a URL across proxies. A
  large scanning session with many `needs_review` sheets silently truncates the list.
- **Suggested fix:** Cap the link (e.g. first 40 ids) with a note, or `POST` the id list
  into `sessionStorage` / a client store and have `/scan/review` read from there, or add
  a real backend filter (`GET /quizzes/{id}/submissions?since=<session start ts>` or an
  explicit id-list body).
- **Tests to add:** unit test of the link builder at 100 ids.

### C6. Low-resolution camera: retake prompt implies retrying will help
- **Severity:** P3  **Confidence:** high
- **Location:** `web/app/(app)/scan/page.tsx:21, 136-141`
- **Symptom:** `MIN_CAPTURE_DIMENSION_PX = 720`; a fixed-480p webcam trips
  "Camera resolution too low to scan reliably — retake." on every capture. Retaking with
  the same device never clears it.
- **Suggested fix:** Detect this once when the stream starts (`video.videoWidth/Height`
  after `loadedmetadata`) and show a persistent, distinct message ("This camera is too
  low-resolution to scan — use a phone camera"), separate from the retake prompt, and
  disable the capture button in that state.
- **Tests to add:** test with a mocked low-res video track.

### C7. In-session summary freezes each sheet's status at submit time
- **Severity:** P3  **Confidence:** high
- **Location:** `web/lib/scan/summary.ts:15-30`, driven by
  `web/lib/scan/useScanQueue.ts` `sheet.result`
- **Symptom:** After the professor follows "Review N flagged" and resolves items, the
  scan screen's "Needs review" count and sheet labels still show the original status —
  `sheet.result.status` is never refreshed. Arguably acceptable for an "in-session"
  tally but can read as the review not having worked.
- **Suggested fix:** Either label the panel explicitly as "at time of scan", or, when the
  scan screen regains focus, re-fetch the `needs_review` sheets' current status and
  update counts.
- **Tests to add:** n/a unless behavior changes.

### C8. Blur threshold calibrated from a single real sample
- **Severity:** P3  **Confidence:** medium
- **Location:** `web/lib/scan/imageQuality.ts:26-49` (`BLUR_THRESHOLD = 150`)
- **Symptom:** Self-documented: lowered from 500 to clear exactly one real sharp capture
  (`sharpnessScore=361` observed once); no genuinely-blurry real sample was ever measured
  to bound the other side. The "good image passes / blurry image retakes" DoD for 7c.2
  rests on synthetic checkerboard fixtures. Risk is bounded (backend confidence gate is
  the real safety net) but the local pre-check may pass real blurry frames or reject
  borderline-fine ones.
- **Suggested fix:** Collect a handful of real captures (sharp + deliberately blurry) via
  the diagnostic save path (`SCAN_DIAG_SAVE_DIR`, `scan.py:55-67`), re-derive the
  threshold, and add them as fixtures to `tests/lib/scan/imageQuality.test.ts`.
- **Tests to add:** real-image fixtures (sharp + blurry) with asserted verdicts.

### C9. `useScanQueue` never releases captured blobs; per-capture main-thread work is heavy
- **Severity:** P3  **Confidence:** medium
- **Location:** `web/lib/scan/useScanQueue.ts:26-33, 66-85`;
  `web/app/(app)/scan/page.tsx:128-165`
- **Symptom:** `blobsRef` retains every captured JPEG (200 KB–1 MB each) for the life of
  the page, including successfully-submitted ones, so they can be retried — but submitted
  sheets never need retry. A long batch (dozens of sheets) holds tens of MB. Separately,
  `capture()` runs `ctx.getImageData` on a full-res frame plus two full-size
  `Float64Array` allocations in `laplacianVariance` (`imageQuality.ts:84-109`)
  synchronously on the main thread every capture — visible jank on a phone.
- **Suggested fix:** Drop the blob from `blobsRef` once a sheet reaches `submitted`.
  Downscale the frame (e.g. to ~1280px on the long edge) before the quality check;
  optionally move the check to a worker or `requestIdleCallback`.
- **Tests to add:** unit test asserting the blob map shrinks after a successful submit.

### C10. `layout.tsx` does a network `getUser()` on every app navigation
- **Severity:** P3  **Confidence:** high
- **Location:** `web/app/(app)/layout.tsx:8-11` (also `account/page.tsx:4-7`)
- **Symptom:** `supabase.auth.getUser()` validates against the Supabase Auth server. The
  layout runs it on every navigation within `(app)`, on top of `proxy.ts`'s own
  `getUser()` for the same request — two Auth round-trips per navigation.
- **Suggested fix:** In the layout, `getSession()` (local, cookie-only) is enough to show
  the email; `proxy.ts` already does the authoritative `getUser()` gate. Or read the user
  once in the layout and pass down.
- **Tests to add:** n/a (perf); optionally assert only one Auth call per navigation.

### C11. Auth error strings shown verbatim and URL-persisted
- **Severity:** P3  **Confidence:** high
- **Location:** `web/app/login/actions.ts:14-16` + `web/app/login/page.tsx:8-24`;
  `web/app/signup/actions.ts:14-16` + `web/app/signup/page.tsx`
- **Symptom:** The raw Supabase error message is put in `?error=` and rendered. It's
  React-escaped (no XSS), but the text is implementation-flavored ("Invalid login
  credentials", rate-limit copy) and persists in the URL — reload/refresh/share re-shows
  it.
- **Suggested fix:** Map known error codes to friendly copy; pass a short error *code*
  in the query, not the message; clear it after display.
- **Tests to add:** action unit tests mapping representative Supabase errors.

### C12. `useReachability` can log a hydration warning when first loaded offline
- **Severity:** P3  **Confidence:** low
- **Location:** `web/lib/scan/useReachability.ts:12-14`
- **Symptom:** SSR renders with `online = true` (no `navigator`); the client `useState`
  initializer reads `navigator.onLine`. If the page first loads while actually offline,
  the first client render differs → React hydration mismatch warning (and a flash).
- **Suggested fix:** Initialize `online` to `true` always and set the real value in a
  mount `useEffect` (already effectively what the effect does — just drop the initializer
  branch), so server and first client render agree.
- **Tests to add:** n/a.

### C13. Misc cleanup
- **Severity:** P3  **Confidence:** high
- `web/components/Card.tsx` — unused (no importers).
- `web/vitest.config.ts` — triggers a Vite "ESM in CJS" deprecation warning on every
  run; rename to `vitest.config.mts` or add `"type": "module"` to `web/package.json`.
- `web/next.config.ts` — empty scaffold comment `/* config options here */`; will hold
  the headers from A4.
- `backend/app/main.py:10-15` — CORS comment describes "the Flutter web client" /
  `flutter run -d chrome`; update to Next.js / Vercel.
- `web/app/(app)/scan/page.tsx:23-32` and `web/lib/scan/scanApi.ts:1-6` — comments assert
  an "anonymous professor session" scan mode that `proxy.ts` makes unreachable on the
  web; correct or remove when A2 is resolved.
- `web/app/(app)/results/[id]/page.tsx:44-50` — `sortKey === "status"` sorts by
  `status.localeCompare` with no stable secondary key (rows with equal status reorder
  arbitrarily between renders); add `created_at` as a tiebreaker.

---

## Not bugs (checked, ruled out)

- **Naive-datetime timezone skew** — `submissions.created_at` / `quizzes.created_at` are
  `timestamptz`; psycopg returns tz-aware datetimes and `.isoformat()` includes the
  offset, so `new Date(...)` in the browser parses them correctly.
- **`create_submission` idempotency race** — the `on conflict (capture_id) ... do nothing`
  + re-select handles concurrent same-capture_id retries correctly.
- **`_recompute_submission_status` leaving `total_score` stale on the `needs_review`
  branch** — the correction endpoints only ever clear flags (`flagged = false` /
  `name_flagged = false`), so a submission cannot move finalized → needs_review via them;
  `total_score` stays `None` through partial review by design and is set correctly when
  the last gate clears.
- **`middleware.ts` open-redirect via `?error=`** — value is only rendered as escaped
  text, never used as a redirect target.
