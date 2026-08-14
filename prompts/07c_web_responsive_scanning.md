# Phase 7c — Responsive web app absorbs scanning (mobile-optional)

## Objective
Extend the Next.js web app (Phase 7 / `07_web_app_nextjs.md`) so it is fully responsive
and becomes the **primary** client for every professor workflow, including live camera
scanning — not just quiz creation and review. The Flutter mobile app (`08_mobile_app.md`)
is **not removed**; it remains available as an optional, legacy scanning client for
professors who want offline batch-scan + local queue behavior. The web app does **not**
attempt offline queueing in this phase — scanning via the browser requires live
connectivity, by explicit decision (see Section below).

Read `claude.md` fully before starting, especially Section 1 ("Two clients, one backend")
and Section 2 (non-negotiable rules — no LLM calls anywhere still applies to every part of
this phase). At the end of this phase, update `claude.md` Section 1 and Section 9 to
reflect the new client relationship described below.

## Decisions locked for this phase (do not re-litigate without asking the user)
- **Flutter mobile app status:** optional/legacy. It still exists, still works, still owns
  the offline-queue + background-sync behavior from Phase 8. It is no longer the only way
  to scan, and its DoD from `08_mobile_app.md` remains valid and unchanged.
- **Web scanning offline behavior:** none for v1. The web app requires live connectivity to
  submit a scan. There is no local queue, no background sync, and no "pending upload"
  state in the web client. If connectivity is lost mid-session, the capture flow must
  block or clearly warn — it must never silently drop a scan or claim success without a
  confirmed round-trip to `POST /scan`.
- **Why:** iOS Safari does not support the Background Sync API and evicts IndexedDB
  unpredictably outside an installed PWA, so a browser-based offline queue can't meet the
  same reliability bar as the native app. Rather than build a false guarantee, the web
  scanning path trades offline support for simplicity, and professors who need offline
  batch-scanning in poor-connectivity venues are pointed to the Flutter app.

## Subtask 7c.1 — Responsive layout pass on existing professor screens
**Steps:**
- Audit every screen shipped in `07_web_app_nextjs.md` (auth/shell, quiz creation, version
  download, results dashboard, flagged-answer review) against three breakpoints: mobile
  (~375–430px), tablet (~768px), desktop (≥1024px).
- Fix any layout that breaks, truncates, or requires horizontal scrolling at the mobile
  breakpoint. Navigation collapses to a mobile-appropriate pattern (e.g. bottom nav or
  hamburger) below the tablet breakpoint.
- Tables (results dashboard) must degrade to a stacked/card layout on mobile rather than
  horizontally scrolling a wide table.

**Definition of Done:**
- [ ] Each existing screen renders with no horizontal overflow and all interactive
      elements reachable/tappable at 375px width, verified with an automated viewport test
      (e.g. Playwright at 375/768/1024px) per screen, not just manual resizing.
- [ ] Results dashboard's card/stacked mobile view shows the same data fields as the
      desktop table, verified by asserting identical field values across both layouts for
      the same seeded submission.

## Subtask 7c.2 — Browser camera capture screen
**Steps:**
- New route, e.g. `/scan`, mobile-viewport-first: full-viewport camera preview via
  `getUserMedia` (rear camera preferred via `facingMode: 'environment'`), capture button.
- On capture, run the same fast local pre-check from Phase 8.2 (QR visible in-frame,
  basic blur detection) client-side in TypeScript before allowing submission — port the
  logic/thresholds, don't redesign them.
- If a blurry or QR-less frame is captured, show an inline retake prompt, same UX contract
  as Phase 8.2.
- Handle camera permission denial and no-camera-available (e.g. desktop without a webcam)
  with a clear, distinct message — do not silently fail.

**Definition of Done:**
- [ ] A deliberately blurred test image fed through the same detection logic used in
      Phase 8.2 triggers the retake prompt (reuse or port Phase 8.2's test fixture).
- [ ] A good test image proceeds without a false-positive retake prompt.
- [ ] Camera permission denial shows a distinct, actionable error state, verified by a
      test that mocks `getUserMedia` rejection.

## Subtask 7c.3 — Direct, connectivity-required scan submission
**Steps:**
- On a passing local pre-check, immediately `POST /scan` with the captured image. Show a
  clear in-progress state until the backend responds.
- Before allowing capture, and continuously during the session, check `navigator.onLine`
  plus a lightweight reachability ping to the backend. If offline or unreachable, disable
  the capture button and show a persistent "no connection — scanning unavailable" banner
  rather than letting the professor capture into a void.
- If a submitted scan's request fails mid-flight (network drop after capture, before a
  response), the UI must clearly mark that specific sheet as "not submitted — retry" and
  let the professor retry it manually. It must never be silently counted as processed.
- No IndexedDB/localStorage queue, no background sync worker — explicitly out of scope
  per the locked decision above.

**Definition of Done:**
- [ ] Simulating offline (mock `navigator.onLine = false` / intercept fetch failure)
      disables capture and shows the banner, verified by a test.
- [ ] Simulating a network failure after capture but before response marks that sheet
      "not submitted — retry" and does not increment any success/finalized counter,
      verified by a test asserting the exact UI/count state.
- [ ] A manual retry on a failed sheet successfully resubmits and updates state correctly.

## Subtask 7c.4 — In-session batch summary
**Steps:**
- Within the same `/scan` session, show a running summary as sheets are processed: total
  attempted, finalized count, needs_review count, failed/not-submitted count.
- Since this is the same app as the review UI (unlike mobile, which hands off to web),
  provide a direct link from the summary into the flagged-answer review screen
  (Phase 7's Subtask 7.5) for any needs_review items from this session.

**Definition of Done:**
- [ ] Summary counts exactly match backend submission statuses for the session's batch,
      verified against seeded/test data (same bar as Phase 8.4's DoD).
- [ ] The "review flagged" link lands on the correct filtered view containing exactly
      this session's needs_review submissions.

## Subtask 7c.5 — Document the two-client relationship
**Steps:**
- Add a short section to `claude.md` (Section 1) clarifying: the responsive web app is
  the primary client for all workflows including scanning; the Flutter mobile app remains
  available as an optional client specifically for offline/poor-connectivity batch
  scanning; both submit to the same `/scan` endpoint and share the same backend/data model
  unchanged.
- Update `claude.md` Section 9 (phase index) to insert this file between Phase 7 and
  Phase 9, and note Phase 8 as "optional/legacy, unchanged."
- No changes required to the backend, database schema, or scoring logic — this phase is
  client-only.

**Definition of Done:**
- [ ] `claude.md` Section 1 and Section 9 updated and committed.
- [ ] Re-confirm no code in this phase makes any LLM call anywhere (Section 2, Rule 1) —
      log the confirmation in `PROGRESS.md`.

## Phase 7c Definition of Done
- [ ] All subtask DoD boxes checked.
- [ ] `08_mobile_app.md`'s own Phase DoD is unaffected and still stands independently —
      this phase does not modify or deprecate the mobile app's functionality.
- [ ] PROGRESS.md updated, code committed.

## Next
Open `09_integration_testing.md`. When writing Phase 9's E2E tests, add a scan-path
variant that exercises `/scan` submission via the web app's flow (not just the previously
assumed mobile path), including the offline-disabled and retry states from Subtask 7c.3.
