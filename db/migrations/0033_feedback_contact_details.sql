-- 0033 - The feedback questionnaire keeps a first name, surname and email too.
--
-- WHY THIS EXISTS
-- The owner decided (27 Nov 2026) that every family who completes the
-- questionnaire gives their name and surname, and a cellphone number or an
-- email address, so the office can follow up and see them all under Growth in
-- the portal. 0032 kept a single optional `name` and an optional `mobile`.
--
-- WHAT IT DOES
-- Adds first_name, surname and email to feedback_responses. The API now
-- requires first_name, surname and at least one of mobile or email, and
-- records contact_consent (the page says giving them is agreeing to be
-- contacted about the feedback). `name` stays, filled with "first surname",
-- so responses saved before this keep showing.
--
-- The consent check is widened to the new columns: no contact detail is kept
-- without contact_consent. It is not made NOT NULL here: responses saved under
-- 0032 may be anonymous, and the API is what requires the details from now on.
--
-- No new grant: the columns are covered by 0032's table grants to induduzo_api,
-- and nothing is granted to anon or authenticated. Safe to run again.

alter table feedback_responses
  add column if not exists first_name text check (char_length(first_name) between 1 and 80),
  add column if not exists surname    text check (char_length(surname) between 1 and 80),
  add column if not exists email      text check (email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'
                                                  and char_length(email) <= 255);

alter table feedback_responses
  drop constraint if exists feedback_responses_details_need_consent;
alter table feedback_responses
  add constraint feedback_responses_details_need_consent
  check (contact_consent or (name is null and mobile is null and first_name is null
                             and surname is null and email is null));

comment on column feedback_responses.first_name is
  'Required by the API since 0033. Null only on responses saved before it.';
comment on column feedback_responses.email is
  'Optional, but the API requires mobile or email since 0033.';

-- Growth lists the families who answered, newest first.
create index if not exists feedback_responses_named_idx
  on feedback_responses (created_at desc) where contact_consent;
