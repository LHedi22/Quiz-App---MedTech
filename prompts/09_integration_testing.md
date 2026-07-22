# Phase 9 — End-to-end integration testing

## Objective
Prove the entire system works together, from Excel upload through to a finalized or
flagged submission, across both clients and the real backend (test environment).

## Subtask 9.1 — Full happy-path E2E test
**Steps:**
- Script or test suite that: uploads a real Excel fixture → generates 3 versions →
  downloads each PDF → simulates scanning each version (using synthetic "filled" bubble
  images generated from the known template) → asserts all 3 submissions finalize with the
  mathematically correct scores.

**Definition of Done:**
- [ ] This test passes end-to-end against a real (test/staging) Supabase + backend
      deployment, not just mocked components.

## Subtask 9.2 — Full unhappy-path E2E test
**Steps:**
- Same flow, but inject: one malformed Excel row, one version scan with an ambiguous
  bubble, one scan with an unreadable QR.
- Assert each failure is handled exactly as specified in earlier phases (structured Excel
  error, needs_review status with correct flagged answer, distinct QR-failure signal).

**Definition of Done:**
- [ ] All three unhappy paths produce the exact expected system state, verified by
      assertions against real DB rows, not just "no crash."

## Subtask 9.3 — Load/volume sanity check
**Steps:**
- Generate a larger quiz (e.g. 50 questions) and a larger version count (e.g. 30) and
  confirm generation, PDF rendering, and scanning still complete within a reasonable time
  bound (define the bound and assert against it, don't leave it vague).

**Definition of Done:**
- [ ] 30-version generation + PDF rendering completes within the defined time bound.
- [ ] No memory or correctness degradation observed at this scale (spot-check a few
      versions' mappings for correctness, not just "it didn't crash").

## Phase 9 Definition of Done
- [ ] All subtask DoD boxes checked.
- [ ] PROGRESS.md updated, code committed.

## Next
Open `10_deployment.md`.