-- 0032 - The homepage banner staff edit, and the private feedback questionnaire.
--
-- WHY THIS EXISTS
-- The owner asked (26 Nov 2026) for two things on the public website:
--
-- 1. A homepage banner staff change from the portal: a photo and the words over
--    it, live on the site at once, with no developer and no redeploy.
-- 2. A short questionnaire that is NOT on the website. It opens only from its
--    own link, which the office prints as a QR code and passes on to families.
--    The owner's post-funeral survey: ten questions (or a five-question short
--    version), an optional name and number, then thanks.
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
-- The owner's "Post-Funeral Family Feedback" survey (26 Nov 2026), in English
-- and isiZulu: ten questions, five of them (marked short) also making up a
-- short version at ?v=short. feedback_surveys has one row: the title, the
-- introduction, the questions and the secret part of the link. The code is made
-- by the database the first time this runs, so it is never in this public
-- repository. Staff replace it from the portal, which stops the old link and
-- every printed QR code at once.
--
-- A question is one of: choice (pick one), scale (1-5 or 0-10, with words at
-- each end), grid (rate several things on the same choices) or text. Each
-- carries both languages; staff edit them in the portal.
--
-- feedback_responses holds what people send. Answering is voluntary and so is
-- giving a name and number: a response may be anonymous. When a name or number
-- is given, contact_consent is true, because the page says plainly that giving
-- them is agreeing to be contacted about the feedback (the owner's wording).
-- The questions' wording is copied into each answer, so changing a question
-- later never changes what an earlier family was asked. No ID number, no bank
-- details: nothing asks for them.
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
  title_en    text not null check (char_length(title_en) between 1 and 120),
  title_zu    text check (char_length(title_zu) between 1 and 120),
  intro_en    text not null check (char_length(intro_en) between 1 and 1000),
  intro_zu    text check (char_length(intro_zu) between 1 and 1000),
  -- See THE QUESTIONNAIRE above. The API checks each question's shape.
  questions   jsonb not null check (
                jsonb_typeof(questions) = 'array'
                and jsonb_array_length(questions) between 1 and 15),
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
  -- Both optional: a family may answer anonymously.
  name            text check (char_length(name) between 1 and 120),
  mobile          text check (mobile ~ '^\+[1-9][0-9]{7,14}$'),
  -- [{"id": "q2", "kind": "scale", "question": "<wording shown>", "answer": ..., "label": "..."}]
  answers         jsonb not null check (jsonb_typeof(answers) = 'array'),
  contact_consent boolean not null default false,
  -- full: all the questions. short: the five marked short.
  version         text not null default 'full' check (version in ('full', 'short')),
  -- How they arrived: the printed QR code, or the link passed on.
  source          text not null default 'link' check (source in ('qr', 'link')),
  language        text not null default 'en' check (language in ('en', 'zu')),
  created_at      timestamptz not null default now(),

  -- A name or number is only kept with the agreement to be contacted.
  constraint feedback_responses_details_need_consent
    check (contact_consent or (name is null and mobile is null))
);

comment on table feedback_responses is
  'Answers to the private feedback questionnaire. Name and mobile are optional; when given, contact_consent is true.';

create index if not exists feedback_responses_created_idx on feedback_responses (created_at desc);
create index if not exists feedback_responses_survey_idx on feedback_responses (survey_id);

-- The owner's survey. The link code comes from gen_random_uuid(), whose first
-- twelve hex digits are all random.
insert into feedback_surveys (link_code, title_en, title_zu, intro_en, intro_zu, questions, updated_by)
select substr(replace(gen_random_uuid()::text, '-', ''), 1, 12),
       'Post-Funeral Family Feedback',
       'Imibono Yomndeni Ngemva Komngcwabo',
       'We are sorry for your loss, and thank you for trusting Induduzo with your family''s farewell. Your honest feedback helps us serve the next family better. Answering is voluntary. Your answers are used only to improve our service and to follow up if you ask us to.',
       'Sidlulisa amazwi enduduzo ngokushonelwa kwenu, futhi siyabonga ngokusethemba ukuthi sisize umndeni wenu ukuphelezela othandekayo wenu. Imibono yenu eqotho isisiza ukuba sisebenzele kangcono umndeni olandelayo. Ukuphendula kuwukuzithandela. Izimpendulo zenu zizosetshenziselwa kuphela ukuthuthukisa umsebenzi wethu nokunilandelela uma nicela.',
       '[
  {"id": "q1", "kind": "choice", "short": false, "required": false, "text_en": "Which branch assisted your family?", "text_zu": "Yiliphi igatsha elisize umndeni wakho?", "options": [{"value": "edendale", "en": "Edendale Main Road (Head Office)", "zu": "Edendale Main Road (Ihhovisi Elikhulu)"}, {"value": "boshoff", "en": "161 Boshoff Street", "zu": "161 Boshoff Street"}, {"value": "langalibalele", "en": "Longmarket (171 Langalibalele Street)", "zu": "Longmarket (171 Langalibalele Street)"}, {"value": "not_sure", "en": "Not sure", "zu": "Angiqiniseki"}]},
  {"id": "q2", "kind": "scale", "short": true, "required": false, "text_en": "Overall, how satisfied were you with our service?", "text_zu": "Sekukonke, waneliseke kangakanani ngomsebenzi wethu?", "min": 1, "max": 5, "low_en": "Very unhappy", "low_zu": "Anganelisekile neze", "high_en": "Very satisfied", "high_zu": "Nganeliseke kakhulu"},
  {"id": "q3", "kind": "scale", "short": true, "required": false, "text_en": "Our staff treated your family with dignity, respect and compassion.", "text_zu": "Abasebenzi bethu bawuphathe umndeni wakho ngesizotha, ngenhlonipho nangozwelo.", "min": 1, "max": 5, "low_en": "Strongly disagree", "low_zu": "Angivumi neze", "high_en": "Strongly agree", "high_zu": "Ngivuma kakhulu"},
  {"id": "q4", "kind": "choice", "short": false, "required": false, "text_en": "Were the services and costs explained clearly before the funeral?", "text_zu": "Ingabe izinsizakalo nezindleko zachazwa kahle ngaphambi komngcwabo?", "options": [{"value": "yes_fully", "en": "Yes, fully", "zu": "Yebo, ngokuphelele"}, {"value": "partly", "en": "Partly", "zu": "Ngokwengxenye"}, {"value": "no", "en": "No", "zu": "Cha"}]},
  {"id": "q5", "kind": "choice", "short": false, "required": false, "text_en": "How easy was the paperwork or policy claim process?", "text_zu": "Kwakulula kangakanani ukugcwalisa amaphepha noma ukufaka isicelo semali yomshwalense?", "options": [{"value": "very_easy", "en": "Very easy", "zu": "Kwakulula kakhulu"}, {"value": "easy", "en": "Easy", "zu": "Kwakulula"}, {"value": "difficult", "en": "Difficult", "zu": "Kwakulukhuni"}, {"value": "very_difficult", "en": "Very difficult", "zu": "Kwakulukhuni kakhulu"}, {"value": "not_applicable", "en": "Not applicable", "zu": "Akungithinti"}]},
  {"id": "q6", "kind": "choice", "short": true, "required": false, "text_en": "Did our vehicles, staff and equipment arrive on time?", "text_zu": "Ingabe izimoto, abasebenzi nezinto zethu zafika ngesikhathi?", "options": [{"value": "on_time", "en": "Yes, everything was on time", "zu": "Yebo, konke kwafika ngesikhathi"}, {"value": "small_delays", "en": "There were small delays", "zu": "Kube nokubambezeleka okuncane"}, {"value": "serious_delays", "en": "There were serious delays", "zu": "Kube nokubambezeleka okukhulu"}]},
  {"id": "q7", "kind": "grid", "short": false, "required": false, "text_en": "How would you rate each of the following?", "text_zu": "Ungakulinganisa kanjani lokhu okulandelayo?", "rows": [{"value": "casket", "en": "Casket or coffin", "zu": "Ibhokisi likamufi"}, {"value": "vehicles", "en": "Hearse and vehicles", "zu": "Imoto ethwala umufi nezinye izimoto"}, {"value": "equipment", "en": "Tent, chairs and equipment", "zu": "Ithende, izihlalo nezinye izinto"}, {"value": "programmes", "en": "Programmes and notices", "zu": "Amaphrogremu nezaziso zomngcwabo"}, {"value": "staff", "en": "Staff on the day", "zu": "Abasebenzi ngosuku lomngcwabo"}], "options": [{"value": "excellent", "en": "Excellent", "zu": "Kuhle kakhulu"}, {"value": "good", "en": "Good", "zu": "Kuhle"}, {"value": "fair", "en": "Fair", "zu": "Kuphakathi"}, {"value": "poor", "en": "Poor", "zu": "Kubi"}, {"value": "not_used", "en": "Not used", "zu": "Asikusebenzisanga"}]},
  {"id": "q8", "kind": "choice", "short": false, "required": false, "text_en": "Did you receive everything that was promised?", "text_zu": "Ingabe nakuthola konke enakuthenjiswa?", "options": [{"value": "yes", "en": "Yes", "zu": "Yebo"}, {"value": "no", "en": "No (please explain in the last question)", "zu": "Cha (sicela uchaze embuzweni wokugcina)"}, {"value": "not_sure", "en": "Not sure", "zu": "Angiqiniseki"}]},
  {"id": "q9", "kind": "scale", "short": true, "required": false, "text_en": "How likely are you to recommend Induduzo to family or friends?", "text_zu": "Maningi kangakanani amathuba okuthi utusele umndeni noma abangani i-Induduzo?", "min": 0, "max": 10, "low_en": "Not at all likely", "low_zu": "Cha neze", "high_en": "Extremely likely", "high_zu": "Nakanjani"},
  {"id": "q10", "kind": "text", "short": true, "required": false, "text_en": "What did we do well, and what should we improve?", "text_zu": "Yikuphi esikwenze kahle, futhi yikuphi okufanele sikuthuthukise?"}
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
  -- A response is written once and never changed.
  grant select, insert         on feedback_responses    to induduzo_api;

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
