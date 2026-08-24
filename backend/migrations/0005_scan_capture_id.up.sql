-- Idempotent /scan submissions.
--
-- A client (web's manual Retry, mobile's automatic exponential-backoff
-- sync) can retry a scan whose response was lost even though the server
-- already created a submission - found via a real end-to-end run where an
-- httpx.ReadTimeout on a slow OMR pass was followed by a retry that
-- duplicated an already-successful submission. capture_id is an optional,
-- client-generated id sent with every attempt for the same physical
-- capture (including retries); a partial unique index lets the backend
-- insert-or-fetch atomically instead of creating a second row. Callers that
-- don't send one (or predate this column) are unaffected - null values
-- never collide with each other or with a real id.

alter table submissions
  add column capture_id text;

create unique index submissions_capture_id_key
  on submissions (capture_id)
  where capture_id is not null;
