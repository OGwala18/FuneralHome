-- 0003 — The person-capture table for the two-stage join flow.
--
-- Stage 1 (lead) columns are NOT NULL where the form requires them.
-- Stage 2 (application) columns are all nullable, because a lead that never
-- completes stage 2 is still a valid, useful row — that is the whole point of
-- splitting the form into two.
--
-- Deliberately absent: bank account numbers, branch codes, card details.
-- Those are collected by the payment provider, never by us. See AIA 03 §6 and
-- the Induduzo claims framework ("do not handle raw card data yourself").
--
-- Column set derived from data-to-knowledge/domains/funeral_policy.yaml so that
-- this table maps cleanly onto the policy/member warehouse tables later.

create sequence plan_enquiry_ref_seq start 1000;

create table plan_enquiries (
  -- Skeleton required on every AIA business table (foundation 03 §5.1)
  id                      uuid primary key default gen_random_uuid(),
  tenant_id               uuid not null default '00000000-0000-0000-0000-000000000001',
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now(),
  archived_at             timestamptz,

  -- Human-quotable reference for phone follow-ups: IND-2026-001000
  reference               text not null unique
                            default 'IND-' || to_char(now(), 'YYYY') || '-'
                                 || lpad(nextval('plan_enquiry_ref_seq')::text, 6, '0'),

  -- Workflow position
  stage                   enquiry_stage  not null default 'lead',
  status                  enquiry_status not null default 'new',

  -- ---------- STAGE 1: contact capture (always present) ----------
  first_name              text not null check (length(trim(first_name)) between 1 and 100),
  surname                 text not null check (length(trim(surname))    between 1 and 100),
  mobile_number           text not null check (mobile_number ~ '^(\+?27|0)[6-8][0-9]{8}$'),
  email                   text          check (email is null or email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'),
  city                    text,
  suburb_or_town          text,
  province                text,
  language_preference     preferred_language not null default 'zu',
  plan_interest           plan_code          not null default 'unsure',
  best_contact_time       text,
  how_heard               text,   -- funnel attribution; Recovery Plan phase 4 scorecard
  source                  text not null default 'website',

  -- POPIA. Contact consent gates any follow-up at all; marketing consent is a
  -- separate, explicit opt-in and must never be implied by the first.
  contact_consent         boolean not null default false,
  marketing_consent       boolean not null default false,
  consented_at            timestamptz,

  -- ---------- STAGE 2: full application (nullable until submitted) ----------
  id_number               text check (id_number is null or id_number ~ '^[0-9]{13}$'),
  date_of_birth           date,
  marital_status          marital_status,
  address_line1           text,
  address_line2           text,
  postal_code             text,

  cover_area              cover_area,
  plan_selected           plan_code,
  coffin_choice           coffin_option,
  age_band                text,             -- e.g. '21-45', only meaningful for Plan C

  -- Money as integer minor units + explicit currency (AIA 03 §5.2). Never a float.
  premium_amount_cents    bigint check (premium_amount_cents is null or premium_amount_cents >= 0),
  currency                char(3) not null default 'ZAR',
  payment_frequency       payment_frequency,
  payment_preference      payment_preference,

  number_of_dependants    smallint check (number_of_dependants is null
                                          or number_of_dependants between 0 and 20),

  next_of_kin_name         text,
  next_of_kin_mobile       text,
  next_of_kin_relationship text,

  beneficiary_name         text,
  beneficiary_mobile       text,
  beneficiary_relationship text,

  notes                    text,
  terms_accepted           boolean not null default false,

  -- ---------- Lifecycle timestamps ----------
  lead_submitted_at        timestamptz not null default now(),
  application_submitted_at timestamptz,

  -- WhatsApp confirmation (Twilio). We store the provider's message id so a
  -- delivery webhook can be reconciled back to this row idempotently.
  whatsapp_sent_at         timestamptz,
  whatsapp_message_sid     text,

  -- An application cannot be marked submitted without the consent that legally
  -- permits us to process it.
  constraint application_requires_consent
    check (stage <> 'application' or (contact_consent and terms_accepted)),

  -- If it reached application stage, it must carry a submission timestamp.
  constraint application_requires_timestamp
    check (stage <> 'application' or application_submitted_at is not null)
);

comment on table plan_enquiries is
  'Two-stage funeral plan capture. Stage 1 (lead) is retained for follow-up even when stage 2 is never completed. Contains POPIA-protected personal information; no banking or card data is stored here.';

-- Indexes the staff follow-up queue will actually use.
create index plan_enquiries_tenant_status_idx  on plan_enquiries (tenant_id, status)
  where archived_at is null;
create index plan_enquiries_created_idx        on plan_enquiries (created_at desc);
create index plan_enquiries_mobile_idx         on plan_enquiries (mobile_number);
create index plan_enquiries_email_idx          on plan_enquiries (lower(email))
  where email is not null;
create unique index plan_enquiries_id_number_idx on plan_enquiries (id_number)
  where id_number is not null and archived_at is null;

-- Keep updated_at honest. SECURITY INVOKER: a trigger function must not be
-- callable as a privileged RPC.
create or replace function set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

revoke all on function set_updated_at() from public, anon, authenticated;

create trigger plan_enquiries_set_updated_at
  before update on plan_enquiries
  for each row execute function set_updated_at();
