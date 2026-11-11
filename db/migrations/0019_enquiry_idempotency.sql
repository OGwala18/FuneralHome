-- 0019 - A retried form submission must not become a second enquiry.
--
-- WHY THIS EXISTS
-- On a slow phone connection a family taps "Submit" twice, or the browser
-- retries after a timeout that the server actually survived. Before this, each
-- of those became a new lead, a new reference and a new email to the office.
--
-- HOW
--   idempotency_key          Stage 1. The browser makes one random UUID per form
--                            attempt and sends it as the Idempotency-Key header.
--                            The same key always returns the same enquiry; it is
--                            never stored twice (unique index below).
--   idempotency_fingerprint  A SHA-256 of the stage-1 payload. A key replayed
--                            with DIFFERENT details is refused rather than
--                            silently answered with someone else's enquiry.
--   application_fingerprint  Stage 2. A SHA-256 of the application payload. An
--                            identical resubmission returns the saved row and
--                            sends nothing; a real correction still updates.
--
-- The key is a random value the browser invents, so it reveals nothing. The
-- fingerprints are one-way hashes and are never logged.
--
-- WHERE IT RUNS
-- Everywhere plan_enquiries exists, Supabase included. Columns on an existing
-- table inherit its grants, so induduzo_api needs nothing new.

alter table plan_enquiries
  add column if not exists idempotency_key         uuid,
  add column if not exists idempotency_fingerprint text,
  add column if not exists application_fingerprint text;

create unique index if not exists plan_enquiries_idempotency_key_idx
  on plan_enquiries (idempotency_key)
  where idempotency_key is not null;

comment on column plan_enquiries.idempotency_key is
  'Browser-generated UUID for one stage-1 form attempt. Replays return the same enquiry.';
comment on column plan_enquiries.idempotency_fingerprint is
  'SHA-256 of the stage-1 payload, so a key reused with different details is refused.';
comment on column plan_enquiries.application_fingerprint is
  'SHA-256 of the last stage-2 payload, so an identical resubmission changes and sends nothing.';
