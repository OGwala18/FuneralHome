-- 0015 - The business's own phone numbers.
--
-- These are Induduzo's own lines. Members' numbers live in person_phones.
-- The first row is the WhatsApp line bought in October 2026 for the automated
-- messages sent through Twilio.
--
-- A number registered with Twilio as a WhatsApp sender is a business API line.
-- Messages people send to it arrive at Twilio, not on a phone, so `purpose`
-- separates it from a line answered in the WhatsApp app. `whatsapp_status` and
-- `twilio_sender_sid` track the registration, so it is visible here when the
-- line goes live.
--
-- Not personal information, but it still follows SECURITY.md rule 8: no access
-- for `anon` or `authenticated`, only for the API.

create table business_phone_numbers (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null default '00000000-0000-0000-0000-000000000001',

  -- E.164, e.g. +27697060387.
  number_e164       text not null check (number_e164 ~ '^\+[1-9][0-9]{7,14}$'),
  label             text not null check (length(trim(label)) between 1 and 80),
  purpose           text not null check (purpose in
                      ('whatsapp_api',   -- a Twilio WhatsApp sender; replies go to Twilio
                       'whatsapp_app',   -- answered by staff in the WhatsApp app
                       'voice',
                       'emergency')),

  whatsapp_status   text not null default 'not_registered' check (whatsapp_status in
                      ('not_registered', 'pending', 'online', 'offline')),
  -- Twilio's sender id (XE...), once registered.
  twilio_sender_sid text check (twilio_sender_sid is null
                                or twilio_sender_sid ~ '^XE[0-9a-f]{32}$'),

  -- Whether the public website shows it. Informational: the site keeps its
  -- own copy in frontend/src/lib/contact.ts.
  is_public         boolean not null default false,
  notes             text,

  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  archived_at       timestamptz
);

create unique index business_phone_numbers_number_idx
  on business_phone_numbers (number_e164)
  where archived_at is null;

create trigger business_phone_numbers_set_updated_at
  before update on business_phone_numbers
  for each row execute function set_updated_at();

comment on table business_phone_numbers is
  'Induduzo''s own phone lines, including the Twilio WhatsApp sender and its registration state. Not members'' numbers: those are in person_phones.';

insert into business_phone_numbers (number_e164, label, purpose, notes)
values ('+27697060387', 'WhatsApp line', 'whatsapp_api',
        'New SIM, never used on WhatsApp. Bought October 2026 for automated '
        'WhatsApp messages through Twilio. Registration waits on the Twilio '
        'account upgrade.')
on conflict do nothing;

-- Access: the API only.
alter table business_phone_numbers enable row level security;
revoke all on business_phone_numbers from anon, authenticated;

do $guard$
begin
  if not exists (select 1 from pg_roles where rolname = 'induduzo_api') then
    return;
  end if;

  grant select, insert, update on business_phone_numbers to induduzo_api;

  drop policy if exists api_rw_business_phones on business_phone_numbers;
  create policy api_rw_business_phones
    on business_phone_numbers for all
    to induduzo_api
    using      (tenant_id = '00000000-0000-0000-0000-000000000001')
    with check (tenant_id = '00000000-0000-0000-0000-000000000001');
end
$guard$;
