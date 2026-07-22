# Phase 5 — OMR engine + bubble classifier

## Objective
Build the computer-vision + trained-classifier pipeline that takes a scanned page image
and returns, per bubble region, whether it's filled/empty/ambiguous with a confidence
score. No LLM involved anywhere in this phase.

## Subtask 5.1 — Page alignment
**Steps:**
- `app/ml/omr/align.py`: detect fiducial corner markers (print 3–4 small solid squares at
  fixed corners in the PDF template from Phase 4 if not already present — coordinate with
  Phase 4's template config) and compute a homography with OpenCV to correct for scan
  angle/skew/rotation.
- Handle graceful failure: if fiducials can't be found, return a clear "alignment failed"
  result rather than silently producing garbage coordinates.

**Definition of Done:**
- [ ] Given a synthetically rotated/skewed test image (rotate a known-good scan by 5°, 15°,
      30° in a test), alignment recovers bubble coordinates within an acceptable pixel
      tolerance (define and assert a concrete tolerance, e.g. ±3px).
- [ ] Given an image with fiducials deliberately removed/occluded, alignment returns a
      failure result rather than throwing an unhandled exception or silently misaligning.

## Subtask 5.2 — Bubble region extraction
**Steps:**
- Using the bubble coordinate template from Phase 4.2, crop each bubble region from the
  aligned image.

**Definition of Done:**
- [ ] For a known test page, the number of extracted crops exactly matches
      questions × options for that quiz.
- [ ] Crop coordinates visually verified correct on at least 3 sample pages (save cropped
      images to a test-output folder and confirm manually, then lock in the assertion).

## Subtask 5.3 — Bubble fill classifier
**Steps:**
- Collect/generate a labeled dataset of bubble crops: filled, empty, ambiguous (partial
  erasure, light mark, stray mark). If no real scanned data exists yet, generate synthetic
  training data programmatically (render bubbles with varying fill %, noise, rotation) —
  document this clearly in PROGRESS.md as a placeholder to replace with real scans later.
- Train a lightweight classifier (logistic regression on pixel-darkness features, or a
  small CNN) — start with the simplest model that clears the DoD bar; only escalate
  complexity if simple approaches fail the bar.
- Wrap it in `app/ml/omr/classify.py`: `classify_bubble(crop) -> (label, confidence)`.

**Definition of Done:**
- [ ] Held-out test set (not used in training) accuracy ≥ 95% on filled vs. empty
      classification (adjust target only with clear reasoning logged in PROGRESS.md).
- [ ] Ambiguous cases (defined threshold) are correctly routed to low confidence rather
      than confidently misclassified — verify with a dedicated ambiguous-case test subset.
- [ ] Model artifact is saved to disk and loadable by a separate inference script (prove
      train/inference are properly decoupled).

## Subtask 5.4 — QR decode integration
**Steps:**
- `app/ml/omr/qr_decode.py`: wrap `pyzbar`/OpenCV `QRCodeDetector` to extract the `qr_id`
  string from a page image.

**Definition of Done:**
- [ ] For 20 sample rendered-then-photographed (or simulated-photo, e.g. re-encoded with
      compression + slight blur) QR images, decode succeeds and returns the exact
      original `qr_id` string.
- [ ] For a deliberately unreadable/occluded QR test image, the function returns a clear
      failure signal, not an exception or a wrong value.

## Phase 5 Definition of Done
- [ ] All subtask DoD boxes checked.
- [ ] A README in `app/ml/` documents the classifier's training data source, accuracy,
      and known limitations (e.g. "trained on synthetic data, needs real-scan retraining").
- [ ] PROGRESS.md updated, code committed.

## Next
Open `06_scan_grade_service.md`.