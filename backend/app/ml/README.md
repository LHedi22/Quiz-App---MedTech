# app/ml — OMR pipeline & bubble classifier

Phase 5's computer-vision + trained-classifier pipeline: takes a scanned
page image and returns, per bubble region, filled/empty/ambiguous with a
confidence score. No LLM is used anywhere in this package (see CLAUDE.md
Section 2) — every step below is either deterministic OpenCV geometry or a
small `scikit-learn` classifier.

## Layout

- `app/ml/omr/align.py` — detects the four printed corner fiducials and
  computes a homography to correct scan rotation/skew.
- `app/ml/omr/extract.py` — crops individual bubble regions from an aligned
  page image using `app/config/pdf_template.json`'s coordinates.
- `app/ml/omr/qr_decode.py` — crops and decodes the per-version QR code from
  a page image.
- `app/ml/omr/classify.py` — **inference only**. Loads the trained model
  artifact and classifies a single bubble crop. Does not import any
  training code.
- `app/ml/bubble_classifier/` — **training only**.
  - `features.py` — pixel-darkness feature extraction, shared with
    `classify.py` (the one module both sides of the train/inference
    boundary import).
  - `synthetic_data.py` — synthetic bubble-crop generator (see below).
  - `train.py` — fits the classifier and saves `model.joblib`. Run
    standalone: `python -m app.ml.bubble_classifier.train`.
  - `model.joblib` — the committed, trained artifact `classify.py` loads.

## Bubble classifier: training data source

**Entirely synthetic.** No real scanned/photographed exam sheets have been
collected yet, so `synthetic_data.py` programmatically renders bubble crops:
a printed circle outline plus a controllable ink fill (area-proportional to
a target fill fraction), Gaussian pixel noise, and a small random rotation.
Deliberately-hard variants are also generated for the ambiguous-routing
tests: a heavily partially-erased fill, a faint/light mark (attenuated
contrast), a mid-range fill (~35–65%), and a stray mark near an otherwise
empty bubble.

This is a **placeholder**, not a permanent choice — see Known limitations.

## Classifier: model and accuracy

A single `sklearn.linear_model.LogisticRegression` over 5 hand-engineered
pixel-darkness features (whole-crop mean/std darkness, dark-pixel fraction,
and separate inner-disc vs. outer-ring darkness means), computed on a
crop resized to a fixed 32x32 canonical size so results don't depend on
scan DPI. This is the simplest model in the CLAUDE.md prompt's suggested
progression ("logistic regression on pixel-darkness features, or a small
CNN — start with the simplest model that clears the DoD bar"), and it
cleared the bar immediately, so no escalation to a CNN was needed.

- Held-out accuracy (filled vs. empty, stratified 70/30 split): **100%**
  (target: ≥95%, see `backend/tests/test_bubble_classifier.py`).
- Ambiguous-case routing (mid-range fill, faint/light mark, heavy partial
  erasure): **100%** routed to `"ambiguous"` rather than a confident guess,
  against a ≥90% target.
- A stray mark near an otherwise-empty bubble is never confidently
  misclassified as `"filled"` — the specific failure mode that check
  guards against.

`classify_bubble(crop) -> (label, confidence)` returns `"ambiguous"`
whenever the model's top-class probability is below `CONFIDENCE_THRESHOLD`
(0.85 — see `app/ml/omr/classify.py`), independent of which class it leaned
toward.

## Known limitations

- **Synthetic-only training data.** The classifier has never seen a real
  pencil/pen mark, real paper texture, real scanner/phone-camera noise, or
  real lighting variation. It needs retraining (or at least held-out
  validation) on real scanned answer sheets before being trusted in
  production — the 100% synthetic accuracy is a ceiling on "can this model
  learn the synthetic distribution," not evidence it generalizes.
- **Single answer-sheet template.** Feature extraction assumes the
  printed bubble geometry from `app/config/pdf_template.json`; a
  differently-designed answer sheet would need re-validation.
- **Fiducial/finder-pattern collision risk if the template changes.**
  `align.py`'s fiducial size (22pt) was deliberately chosen well above this
  project's QR finder-pattern size (~17pt) so the two aren't confused by a
  naive shape/area detector. Changing `qr_box.size_pt`, the QR error
  correction level, or `fiducials.size_pt` in `pdf_template.json` should be
  re-checked against this margin (see `align.py`'s module comments).
- **No lighting/exposure normalization.** `extract_features` works directly
  on raw pixel darkness; a real scan with strong lighting gradients across
  the page could shift the effective decision boundary. A production
  version should likely normalize each crop (or the whole page) against a
  local background estimate before feature extraction.
