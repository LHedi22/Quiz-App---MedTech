# Phase 4 — PDF generation + QR code embedding

## Objective
For every generated version, produce a print-ready PDF containing the shuffled
questions/options and a QR code encoding that version's `qr_id`, stored in Supabase
Storage and downloadable by the professor.

## Subtask 4.1 — QR code generation
**Steps:**
- `app/services/qr.py`: `generate_qr(version_qr_id: str) -> PNG bytes` using the `qrcode`
  library.
- Confirm the encoded string round-trips: decode the generated QR image and assert it
  matches the input `qr_id` exactly.

**Definition of Done:**
- [ ] For 20 random UUIDs, generate + decode each QR image and assert exact string match.
- [ ] QR image is generated at a resolution/size that remains scannable after being placed
      at a defined size in the PDF (verify by decoding the QR AFTER it's embedded in a
      rendered PDF page image, not just the standalone PNG).

## Subtask 4.2 — PDF layout
**Steps:**
- `app/services/pdf_gen.py`: `render_version_pdf(version, questions) -> PDF bytes` using
  ReportLab or WeasyPrint.
- Layout: header with quiz title + version number, QR code placed in a fixed, consistent
  corner position on every page (needed later for scan-time alignment), each question
  with lettered bubble options (A/B/C/D) rendered as fillable circles.
- Multi-page support: if a quiz has enough questions to span multiple pages, the QR code
  must appear on every page (in case a professor scans a page out of order or a sheet
  gets separated), or the design must otherwise guarantee every scanned page can be
  correctly identified — pick one approach and document why in PROGRESS.md.

**Definition of Done:**
- [ ] Rendered PDF for a 10-question, 4-option quiz has all questions/options legible in
      a rendered screenshot at expected print resolution (manually verify one, then codify
      the check as: page count is correct, question count per page matches expectations).
- [ ] QR code position is pixel-identical (same x/y/size) across every generated PDF for
      the same quiz template, verified by comparing bounding boxes across 3 sample PDFs.
- [ ] Bubble regions have consistent, documented coordinates suitable for later OMR
      alignment (write these coordinates to a template config file, not just implicitly
      in the rendering code).

## Subtask 4.3 — Storage + download endpoint
**Steps:**
- After generating a version's PDF, upload it to Supabase Storage under a path keyed by
  `quiz_id`/`version_id`.
- `GET /versions/{version_id}/pdf` returns a signed download URL or the file directly.

**Definition of Done:**
- [ ] Integration test: after version creation, the PDF exists in storage and is
      downloadable, and its content matches what Subtask 4.2 produces (byte-for-byte or
      hash-matched).
- [ ] Repeated calls to the download endpoint don't regenerate/duplicate the file.

## Phase 4 Definition of Done
- [ ] All subtask DoD boxes checked, including the documented bubble-coordinate template
      config that Phase 5/6 will depend on.
- [ ] PROGRESS.md updated, code committed.

## Next
Open `05_omr_ml_pipeline.md`.