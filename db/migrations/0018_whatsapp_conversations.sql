-- 0018 - The WhatsApp line answers, and hands over to staff.
--
-- WHY THIS EXISTS
-- docs/feature-3-whatsapp-line.md. Families message 073 731 0521 and an
-- automatic menu answers them: seven common topics, each with its own answers.
-- Only when the menu can't help and the family asks for a person does anything
-- reach staff. That is an escalation: it is emailed to the office and shown in
-- the portal, where staff reply from the same number or phone them back.
--
-- FOUR TABLES
--   whatsapp_conversations  one row per family number: where it is in the menu
--   whatsapp_messages       every message, both ways, including confirmations
--   whatsapp_escalations    "a person, please": what staff work from
--   whatsapp_feedback       1-5 ratings, and the words that came with them
--
-- PERSONAL DATA
-- Message text is personal data, and the menu never asks for an ID number. The
-- API strips any run of 13 or more digits (an ID or card number) before a
-- message is stored, so one sent anyway never reaches these tables. How long
-- messages are kept is still open (the plan's §3, before production).
--
-- WHERE IT RUNS
-- Needs plan_enquiries (0003) and people (0009). Like 0013 and 0016, it is not
-- for Supabase until the API's own database there is settled.

-- ---------------------------------------------------------------------------
-- One row per family number. The menu reads and writes `state` on every
-- message, under a row lock, so two quick messages can't both start from the
-- same step.
-- ---------------------------------------------------------------------------
create table whatsapp_conversations (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null default '00000000-0000-0000-0000-000000000001',

  other_number     text not null check (other_number ~ '^\+[1-9][0-9]{7,14}$'),
  profile_name     text,   -- the WhatsApp display name the family chose

  -- A node id in backend/app/services/whatsapp_content.py ('main', 'claims',
  -- 'agent'), or 'idle', 'rating', 'rating_comment' or 'escalated'.
  state            text not null default 'idle',
  -- Where "go back" leads, and which topic a rating is about. Never an ID number.
  data             jsonb not null default '{}',
  -- Replies in a row the menu didn't understand. Two in a row offers a person.
  misses           smallint not null default 0 check (misses >= 0),

  opted_out_at     timestamptz,   -- STOP. START clears it.
  last_inbound_at  timestamptz,   -- 30 minutes' silence restarts the menu, and
                                  -- staff may reply freely for 24 hours after it
  last_message_at  timestamptz not null default now(),

  enquiry_id       uuid references plan_enquiries(id),
  person_id        uuid references people(id),

  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

comment on table whatsapp_conversations is
  'One row per family WhatsApp number: where it is in the automatic menu, and who it is when the number matches an enquiry or a member. Contains personal information.';

create unique index whatsapp_conversations_number_idx
  on whatsapp_conversations (tenant_id, other_number);
create index whatsapp_conversations_enquiry_idx on whatsapp_conversations (enquiry_id)
  where enquiry_id is not null;
create index whatsapp_conversations_person_idx on whatsapp_conversations (person_id)
  where person_id is not null;

create trigger whatsapp_conversations_set_updated_at
  before update on whatsapp_conversations
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- Every message, both ways. Inbound rows are keyed by Twilio's MessageSid, so
-- a webhook delivered twice stores one row and gets one answer.
-- ---------------------------------------------------------------------------
create table whatsapp_messages (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null default '00000000-0000-0000-0000-000000000001',
  conversation_id  uuid references whatsapp_conversations(id),

  direction        text not null check (direction in ('inbound', 'outbound')),
  -- Null only for an outbound message that was never handed to Twilio, for
  -- example one WHATSAPP_OUTBOUND refused. Then error_code says why.
  twilio_sid       text unique,
  -- 'family' for inbound; 'menu', 'system' (the registration confirmation) or
  -- the staff member's email for outbound.
  author           text not null,

  business_number  text not null,
  other_number     text not null check (other_number ~ '^\+[1-9][0-9]{7,14}$'),
  body             text,
  -- [{"sid": "ME...", "content_type": "image/jpeg"}]. Never a URL: a media
  -- URL plus the account's credentials opens the file.
  media            jsonb not null default '[]',
  -- The menu step a message was sent from or answered at, for the statistics.
  menu_node        text,

  -- inbound:  received
  -- outbound: not_sent | queued | sent | delivered | read | failed | undelivered
  status           text not null check (status in
                     ('received', 'not_sent', 'queued', 'sent', 'delivered',
                      'read', 'failed', 'undelivered')),
  error_code       text,

  enquiry_id       uuid references plan_enquiries(id),

  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),

  constraint whatsapp_messages_inbound_has_sid
    check (direction = 'outbound' or twilio_sid is not null),
  constraint whatsapp_messages_inbound_is_received
    check ((direction = 'inbound') = (status = 'received')),
  constraint whatsapp_messages_inbound_is_family
    check ((direction = 'inbound') = (author = 'family'))
);

comment on table whatsapp_messages is
  'Every WhatsApp message to and from the line, both ways. Any run of 13 or more digits is removed before a row is written. Contains personal information.';

-- A conversation's transcript, newest first.
create index whatsapp_messages_conversation_idx
  on whatsapp_messages (conversation_id, created_at desc);
create index whatsapp_messages_enquiry_idx on whatsapp_messages (enquiry_id)
  where enquiry_id is not null;

create trigger whatsapp_messages_set_updated_at
  before update on whatsapp_messages
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- A family asked for a person. One open escalation per conversation at most:
-- asking again updates it rather than emailing the office twice.
-- ---------------------------------------------------------------------------
create table whatsapp_escalations (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null default '00000000-0000-0000-0000-000000000001',
  conversation_id  uuid not null references whatsapp_conversations(id),

  -- How the family asked to be reached.
  channel          text not null check (channel in ('whatsapp', 'call')),
  -- The menu node they were on, and its title, e.g. 'claims' / 'Claims and payouts'.
  topic            text not null,
  topic_label      text not null,
  -- Someone has passed away. Always emailed at once, day or night.
  urgent           boolean not null default false,
  -- Asked outside office hours; promised_for is when the office opens.
  out_of_hours     boolean not null default false,
  promised_for     timestamptz,

  status           text not null default 'open' check (status in ('open', 'resolved')),
  requested_at     timestamptz not null default now(),

  -- The office email. Retried by the backfill job until it goes.
  notified_at      timestamptz,
  notify_error     text,

  first_reply_at   timestamptz,   -- the first staff message from the portal
  resolved_at      timestamptz,
  resolved_by      text,          -- staff email
  resolution_note  text check (length(resolution_note) <= 1000),

  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),

  constraint whatsapp_escalations_resolved_has_date
    check ((status = 'resolved') = (resolved_at is not null))
);

comment on table whatsapp_escalations is
  'WhatsApp conversations a family asked to hand to a person. The only WhatsApp conversations the office is emailed about or shown.';

create unique index whatsapp_escalations_one_open_idx
  on whatsapp_escalations (conversation_id) where status = 'open';
create index whatsapp_escalations_status_idx
  on whatsapp_escalations (status, requested_at desc);
create index whatsapp_escalations_unnotified_idx
  on whatsapp_escalations (requested_at) where notified_at is null;

create trigger whatsapp_escalations_set_updated_at
  before update on whatsapp_escalations
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- Ratings from 1 to 5, after an answer helped, after a compliment, or after
-- staff resolve an escalation. The comment is optional.
-- ---------------------------------------------------------------------------
create table whatsapp_feedback (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null default '00000000-0000-0000-0000-000000000001',
  conversation_id  uuid not null references whatsapp_conversations(id),
  escalation_id    uuid references whatsapp_escalations(id),

  topic            text not null,   -- the menu node that was answered
  rating           smallint check (rating between 1 and 5),
  comment          text check (length(comment) <= 1000),

  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),

  constraint whatsapp_feedback_says_something
    check (rating is not null or comment is not null)
);

comment on table whatsapp_feedback is
  'Ratings and comments families gave over WhatsApp.';

create index whatsapp_feedback_created_idx on whatsapp_feedback (created_at desc);
create index whatsapp_feedback_conversation_idx on whatsapp_feedback (conversation_id);
create index whatsapp_feedback_escalation_idx on whatsapp_feedback (escalation_id)
  where escalation_id is not null;

create trigger whatsapp_feedback_set_updated_at
  before update on whatsapp_feedback
  for each row execute function set_updated_at();

-- ---------------------------------------------------------------------------
-- Access: the API only (SECURITY.md rule 8). Nothing for anon or
-- authenticated. The revoke matters on Supabase, whose default privileges give
-- both roles every new table. No DELETE, as everywhere else for this role: the
-- retention job, once decided, gets its own migration.
-- ---------------------------------------------------------------------------
alter table whatsapp_conversations enable row level security;
alter table whatsapp_messages      enable row level security;
alter table whatsapp_escalations   enable row level security;
alter table whatsapp_feedback      enable row level security;

revoke all on whatsapp_conversations, whatsapp_messages,
              whatsapp_escalations, whatsapp_feedback
  from anon, authenticated;

do $guard$
declare
  tables   text[] := array['whatsapp_conversations', 'whatsapp_messages',
                           'whatsapp_escalations', 'whatsapp_feedback'];
  policies text[] := array['api_rw_whatsapp_conversations', 'api_rw_whatsapp_messages',
                           'api_rw_whatsapp_escalations', 'api_rw_whatsapp_feedback'];
  i int;
begin
  if not exists (select 1 from pg_roles where rolname = 'induduzo_api') then
    return;
  end if;

  for i in 1 .. array_length(tables, 1) loop
    execute format('grant select, insert, update on %I to induduzo_api', tables[i]);
    execute format('drop policy if exists %I on %I', policies[i], tables[i]);
    execute format(
      'create policy %I on %I for all to induduzo_api '
      'using (tenant_id = %L) with check (tenant_id = %L)',
      policies[i], tables[i],
      '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001');
  end loop;
end
$guard$;
