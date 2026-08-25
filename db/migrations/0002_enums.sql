-- 0002 — Enums for the plan enquiry capture flow.
--
-- AIA foundation 03 §5.2: "use a real Postgres enum or a constrained text
-- column, never a magic integer."

-- Which of the two capture stages the record has reached.
create type enquiry_stage as enum (
  'lead',         -- stage 1 complete: we can contact them
  'application'   -- stage 2 complete: they submitted full details
);

-- Operational status. Deliberately a separate axis from stage: a record can be
-- stage='lead' and status='contacted' without ever becoming an application.
create type enquiry_status as enum (
  'new',
  'contacted',
  'application_started',
  'application_submitted',
  'awaiting_payment',
  'active',
  'declined',
  'lost'
);

-- Plans as published on the website. 'unsure' is deliberate: a lead who does not
-- know which plan they want is still a lead worth following up.
create type plan_code as enum (
  'plan_a',
  'plan_b',
  'plan_c',
  'dome_plan',
  'unsure'
);

-- City vs rural burial tier, which is what actually routes Plan A vs Plan B.
create type cover_area as enum (
  'edolobheni',  -- city
  'emakhaya'     -- rural
);

-- Plan C coffin tier.
create type coffin_option as enum (
  'flat_lid',
  'casket'
);

create type preferred_language as enum (
  'zu',  -- isiZulu
  'en',  -- English
  'xh',  -- isiXhosa
  'af',  -- Afrikaans
  'st',  -- Sesotho
  'other'
);

create type payment_frequency as enum (
  'monthly',
  'once_off'
);

-- Preference only. No bank or card details are ever stored in this database;
-- collection is delegated to the payment provider.
create type payment_preference as enum (
  'debit_order',
  'eft',
  'cash',
  'card',
  'undecided'
);

create type marital_status as enum (
  'single',
  'married',
  'customary_union',
  'divorced',
  'widowed',
  'other'
);
