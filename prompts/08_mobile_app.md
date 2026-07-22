# Phase 8 — Mobile app (scanning only)

## Objective
A stripped-down, camera-first Flutter mobile app: sign in, then scan a stack of papers as
fast as possible, with a local queue and sync-to-backend behavior.

## Subtask 8.1 — Auth (minimal)
**Steps:**
- Reuse the same Supabase Auth as web (shared package if monorepo).
- Single sign-in screen, no sign-up flow needed on mobile (professors register on web).

**Definition of Done:**
- [ ] A professor who signed up on web can log in on mobile with the same credentials,
      verified against a real (test) Supabase project.

## Subtask 8.2 — Camera capture screen
**Steps:**
- Full-screen camera view with a capture button.
- On capture, run a fast local pre-check (not the full ML pipeline): is a QR code visible
  in-frame at all? Is the image sufficiently sharp (basic blur detection)? If not, show an
  inline retake prompt before the professor moves to the next sheet.

**Definition of Done:**
- [ ] Capturing a clearly blurry test image triggers the retake prompt (test with a
      deliberately blurred fixture image fed through the same detection logic).
- [ ] Capturing a good test image proceeds without a false-positive retake prompt.

## Subtask 8.3 — Local queue + sync
**Steps:**
- Decide and implement per the CLAUDE.md open question on offline support: captured images
  are queued locally (e.g. local DB or file storage) with a "pending upload" state.
- Background sync uploads queued images to `POST /scan` when connectivity is available,
  updating each queue item's state to "processed" with the result, or "failed" with a
  retry mechanism.

**Definition of Done:**
- [ ] Simulate offline mode: captures still queue correctly, app remains usable, no data
      loss (verify queue persists across app restart in a test).
- [ ] Simulate reconnection: queued items sync automatically without user action, verified
      by mocking the network state and observing the queue drain.
- [ ] A failed upload (simulate backend error) retries with backoff rather than
      silently dropping the item.

## Subtask 8.4 — Batch scan summary screen
**Steps:**
- After a scanning session, show a summary: total scanned, finalized count, needs_review
  count, with a link/handoff pointing the professor to the web app for review (mobile
  itself does not implement the review UI, per the phase split in CLAUDE.md).

**Definition of Done:**
- [ ] Summary counts exactly match the actual backend submission statuses for that batch,
      verified against seeded/test data.

## Phase 8 Definition of Done
- [ ] All subtask DoD boxes checked.
- [ ] `flutter test` passes fully for the mobile app.
- [ ] PROGRESS.md updated, code committed.

## Next
Open `09_integration_testing.md`.