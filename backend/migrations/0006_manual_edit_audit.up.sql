-- Manual-edit audit markers for the results review screen.
--
-- The web results screen now lets a professor open ANY submission (not just
-- the flagged ones) and change ANY student answer or the student name, even
-- on an already-finalized submission. A lightweight marker per corrected
-- value lets the UI show "edited by professor" without a full history log:
--
--   answers.manually_edited   - true once a professor has set this answer's
--                               marked option by hand (blank included).
--   answers.edited_at         - when that last happened (nullable: never
--                               edited by hand -> null).
--   submissions.name_manually_edited - same idea for the student-name field,
--                               which is now editable at any time, not only
--                               when the OCR read was flagged.
--
-- All three are additive and default to the "never touched by a human"
-- state, so every existing row and the whole OMR pipeline are unaffected.

alter table answers
  add column manually_edited boolean not null default false,
  add column edited_at timestamptz;

alter table submissions
  add column name_manually_edited boolean not null default false;
