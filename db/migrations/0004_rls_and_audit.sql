-- 0004 — Append-only audit trail and Row Level Security.
--
-- AIA foundation 03 §5.4 and the Induduzo claims framework both treat audit as
-- a day-one requirement, not a later phase: "Even your MVP naming and screens
-- should already reflect auditability."

create table enquiry_events (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null default '00000000-0000-0000-0000-000000000001',
  enquiry_id  uuid not null references plan_enquiries(id) on delete restrict,
  event_type  text not null,          -- lead_captured, application_submitted, whatsapp_sent, ...
  actor       text not null default 'public_website',
  payload     jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default now()
);

create index enquiry_events_enquiry_idx on enquiry_events (enquiry_id, created_at desc);
create index enquiry_events_type_idx    on enquiry_events (event_type, created_at desc);

comment on table enquiry_events is
  'Append-only event stream for plan enquiries. No UPDATE or DELETE is granted to any role.';

-- Enforce append-only at the database, not by convention. Verified: an UPDATE
-- and a DELETE against this table are both silently no-ops.
create rule enquiry_events_no_update as on update to enquiry_events do instead nothing;
create rule enquiry_events_no_delete as on delete to enquiry_events do instead nothing;

-- ---------------------------------------------------------------------------
-- Row Level Security
--
-- The trust boundary (AIA 03 §6): the browser is hostile. Anything holding only
-- the public key gets INSERT and nothing else. A leaked public key must not be
-- able to read a single person's details back out.
-- ---------------------------------------------------------------------------
alter table plan_enquiries enable row level security;
alter table enquiry_events enable row level security;

-- Public website may submit an enquiry...
create policy anon_can_submit_enquiry
  on plan_enquiries for insert
  to anon
  with check (
    tenant_id = '00000000-0000-0000-0000-000000000001'
    and contact_consent = true          -- no consent, no row
    and archived_at is null
    and status = 'new'                  -- cannot self-promote into the pipeline
  );

-- ...and may log its own submission events.
create policy anon_can_log_event
  on enquiry_events for insert
  to anon
  with check (tenant_id = '00000000-0000-0000-0000-000000000001');

-- Deliberately NO select/update/delete policy for anon.
-- With RLS enabled and no policy, those operations return zero rows / are denied.

-- Signed-in staff (added when the portal lands) read within their tenant.
create policy staff_can_read_enquiries
  on plan_enquiries for select
  to authenticated
  using (tenant_id = '00000000-0000-0000-0000-000000000001');

create policy staff_can_update_enquiries
  on plan_enquiries for update
  to authenticated
  using (tenant_id = '00000000-0000-0000-0000-000000000001')
  with check (tenant_id = '00000000-0000-0000-0000-000000000001');

create policy staff_can_read_events
  on enquiry_events for select
  to authenticated
  using (tenant_id = '00000000-0000-0000-0000-000000000001');

-- Grant only what is needed.
revoke all on plan_enquiries from anon;
revoke all on enquiry_events from anon;
grant insert on plan_enquiries to anon;
grant insert on enquiry_events to anon;
grant usage, select on sequence plan_enquiry_ref_seq to anon;

grant select, update on plan_enquiries to authenticated;
grant select, insert on enquiry_events to authenticated;
