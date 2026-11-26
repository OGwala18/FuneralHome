-- 0032 - The homepage banner staff edit, and the private feedback questionnaire.
--
-- WHY THIS EXISTS
-- The owner asked (26 Nov 2026) for two things on the public website:
--
-- 1. A homepage banner staff change from the portal: a photo and the words over
--    it, live on the site at once, with no developer and no redeploy.
-- 2. A short questionnaire that is NOT on the website. It opens only from its
--    own link, which the office prints as a QR code and passes on to families.
--    It asks for a name, surname and mobile number, five questions, then thanks
--    the person and asks them to rate the service.
--
-- THE BANNER
-- website_banners is append-only: every save is a new row, and the newest row
-- is what the site shows. A row whose words and photo are all empty means "the
-- standard banner", so going back to it is a save like any other, and the
-- history of who changed the front of the website, and when, is never lost.
-- The API may only SELECT and INSERT it.
--
-- website_banner_images holds the photos themselves, already cropped and
-- resized by the portal to 1920 x 800 (about 200-400 KB each). They live here
-- rather than in a file store so one backup holds everything and a laptop's
-- local database behaves exactly like production. Old photos are emptied
-- (bytes set to null, pruned_at stamped) rather than deleted: the API holds no
-- DELETE anywhere. The API keeps the current photo and the few most recent.
--
-- THE QUESTIONNAIRE
-- feedback_surveys has one row: the questions and the secret part of the link.
-- The code is made by the database the first time this runs, so it is never
-- in this public repository. Staff can replace it from the portal, which stops
-- the old link and old QR codes working at once.
--
-- feedback_responses holds what people send. The questions' wording is copied
-- into each response, so changing a question later never changes what an
-- earlier person was asked. contact_consent must be true, as on the enquiry
-- form (ARCHITECTURE.md §7.5). No ID number, no bank details: nothing asks.
--
-- WHERE IT RUNS
-- Everywhere: the API's own database and Supabase. Grants to induduzo_api are
-- guarded by a pg_roles check, as since 0008. Nothing is granted to anon or
-- authenticated (0026). Safe to run again.

-- ---------------------------------------------------------------- banner ---

create table if not exists website_banner_images (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null default '00000000-0000-0000-0000-000000000001',
  content_type  text not null check (content_type in ('image/jpeg', 'image/webp', 'image/png')),
  -- Null once pruned. The row stays so old banners still say which photo they used.
  bytes         bytea,
  byte_size     integer not null check (byte_size between 1 and 2000000),
  width         integer not null check (width between 1 and 8000),
  height        integer not null check (height between 1 and 8000),
  uploaded_by   text not null,
  created_at    timestamptz not null default now(),
  pruned_at     timestamptz,

  constraint website_banner_images_pruned_means_empty
    check ((bytes is null) = (pruned_at is not null)),
  constraint website_banner_images_size_matches
    check (bytes is null or octet_length(bytes) = byte_size)
);

comment on table website_banner_images is
  'Homepage banner photos uploaded from the staff portal. Pruned photos keep their row with bytes null.';

create index if not exists website_banner_images_created_idx
  on website_banner_images (created_at desc);

create table if not exists website_banners (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null default '00000000-0000-0000-0000-000000000001',
  -- Each blank means "use the website's own wording" for that line.
  headline_en text check (char_length(headline_en) between 1 and 120),
  headline_zu text check (char_length(headline_zu) between 1 and 120),
  message_en  text check (char_length(message_en) between 1 and 300),
  message_zu  text check (char_length(message_zu) between 1 and 300),
  image_id    uuid references website_banner_images (id),
  saved_by    text not null,
  created_at  timestamptz not null default now()
);

comment on table website_banners is
  'Append-only history of the homepage banner. The newest row is live. All-null words and photo = the standard banner.';

create index if not exists website_banners_created_idx on website_banners (created_at desc);
create index if not exists website_banners_image_idx on website_banners (image_id);

-- -------------------------------------------------------- questionnaire ---

create table if not exists feedback_surveys (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null default '00000000-0000-0000-0000-000000000001',
  -- The secret part of https://induduzo.co.za/feedback/<link_code>.
  link_code   text not null unique check (link_code ~ '^[a-z0-9]{10,32}$'),
  -- [{"id": "q1", "kind": "text" | "yes_no" | "scale", "text_en": "...", "text_zu": "..."}]
  questions   jsonb not null check (
                jsonb_typeof(questions) = 'array'
                and jsonb_array_length(questions) between 1 and 10),
  is_open     boolean not null default true,
  updated_by  text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

comment on table feedback_surveys is
  'The private feedback questionnaire: one row. Opens only at /feedback/<link_code>.';

-- One questionnaire per business.
create unique index if not exists feedback_surveys_one_per_tenant on feedback_surveys (tenant_id);

create table if not exists feedback_responses (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null default '00000000-0000-0000-0000-000000000001',
  survey_id       uuid not null references feedback_surveys (id),
  first_name      text not null check (char_length(first_name) between 1 and 80),
  surname         text not null check (char_length(surname) between 1 and 80),
  mobile          text not null check (mobile ~ '^\+[1-9][0-9]{7,14}$'),
  -- [{"id": "q1", "kind": "...", "question": "<wording shown>", "answer": "..."}]
  answers         jsonb not null check (jsonb_typeof(answers) = 'array'),
  contact_consent boolean not null check (contact_consent),
  -- How they arrived: the printed QR code, or the link passed on.
  source          text not null default 'link' check (source in ('qr', 'link')),
  language        text not null default 'en' check (language in ('en', 'zu')),
  rating          smallint check (rating between 1 and 5),
  rating_comment  text check (char_length(rating_comment) between 1 and 1000),
  rated_at        timestamptz,
  created_at      timestamptz not null default now(),

  constraint feedback_responses_rated_together check ((rating is null) = (rated_at is null)),
  constraint feedback_responses_comment_needs_rating check (rating_comment is null or rating is not null)
);

comment on table feedback_responses is
  'Answers to the private feedback questionnaire, with the 1-5 service rating given at the end.';

create index if not exists feedback_responses_created_idx on feedback_responses (created_at desc);
create index if not exists feedback_responses_survey_idx on feedback_responses (survey_id);

-- The questionnaire, with placeholder questions until the owner supplies the
-- real ones; staff replace them in the portal. The link code comes from
-- gen_random_uuid(), whose first twelve hex digits are all random.
insert into feedback_surveys (link_code, questions, updated_by)
select substr(replace(gen_random_uuid()::text, '-', ''), 1, 12),
       '[
          {"id": "q1", "kind": "text",   "text_en": "How did you hear about Induduzo Funeral Home?"},
          {"id": "q2", "kind": "yes_no", "text_en": "Did our staff treat you and your family with care and respect?"},
          {"id": "q3", "kind": "scale",  "text_en": "How easy was it to reach us when you needed us?"},
          {"id": "q4", "kind": "yes_no", "text_en": "Was everything explained clearly: the costs, the plan and the arrangements?"},
          {"id": "q5", "kind": "text",   "text_en": "What could we do better?"}
        ]'::jsonb,
       'migration 0032'
 where not exists (select 1 from feedback_surveys);

-- ------------------------------------------------------------- security ---

alter table website_banner_images enable row level security;
alter table website_banners       enable row level security;
alter table feedback_surveys      enable row level security;
alter table feedback_responses    enable row level security;

revoke all on website_banner_images, website_banners, feedback_surveys, feedback_responses
  from anon, authenticated;

do $guard$
begin
  if not exists (select 1 from pg_roles where rolname = 'induduzo_api') then
    return;
  end if;

  -- Photos: uploaded, read, and emptied when pruned. Never deleted.
  grant select, insert, update on website_banner_images to induduzo_api;
  -- The banner history is append-only for the API.
  grant select, insert         on website_banners       to induduzo_api;
  -- The questions and the link change; the row is never removed.
  grant select, insert, update on feedback_surveys      to induduzo_api;
  -- A response is written once; the rating is added to it afterwards.
  grant select, insert, update on feedback_responses    to induduzo_api;

  drop policy if exists api_rw_website_banner_images on website_banner_images;
  create policy api_rw_website_banner_images on website_banner_images
    for all to induduzo_api
    using (tenant_id = '00000000-0000-0000-0000-000000000001')
    with check (tenant_id = '00000000-0000-0000-0000-000000000001');

  drop policy if exists api_rw_website_banners on website_banners;
  create policy api_rw_website_banners on website_banners
    for all to induduzo_api
    using (tenant_id = '00000000-0000-0000-0000-000000000001')
    with check (tenant_id = '00000000-0000-0000-0000-000000000001');

  drop policy if exists api_rw_feedback_surveys on feedback_surveys;
  create policy api_rw_feedback_surveys on feedback_surveys
    for all to induduzo_api
    using (tenant_id = '00000000-0000-0000-0000-000000000001')
    with check (tenant_id = '00000000-0000-0000-0000-000000000001');

  drop policy if exists api_rw_feedback_responses on feedback_responses;
  create policy api_rw_feedback_responses on feedback_responses
    for all to induduzo_api
    using (tenant_id = '00000000-0000-0000-0000-000000000001')
    with check (tenant_id = '00000000-0000-0000-0000-000000000001');
end
$guard$;
