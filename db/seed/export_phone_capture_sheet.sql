-- The phone capture sheet.
--
-- Run this against the live database and export the result as CSV. It lists
-- everyone who still has no phone number on file, with enough detail to find
-- them in the paper file, and an empty `cell` column for the office to fill in.
--
-- In the Supabase dashboard: SQL Editor, run, then "Download CSV".
-- With psql:
--   \copy (<paste this query>) to 'phone_capture.csv' with (format csv, header)
--
-- Give the CSV back to load_phone_numbers.py when it has been filled in. Do NOT
-- reorder or rename the columns, and do NOT touch person_id: it is the join key,
-- and it is what stops two people with the same name being confused.

select
  pe.id                                        as person_id,
  po.policy_number,
  case when pm.member_type = 'main_member' then 'main member' else '' end as role,
  pe.surname,
  pe.first_names,
  coalesce(pe.initials, '')                    as initials,
  coalesce(pe.id_number, '')                   as id_number,
  coalesce(pe.date_of_birth::text, '')         as date_of_birth,
  ''                                           as cell
from people pe
left join policy_members pm on pm.person_id = pe.id and pm.archived_at is null
left join policies       po on po.id = pm.policy_id
where pe.archived_at is null
  -- Only people we genuinely cannot telephone.
  and not exists (
    select 1 from person_phones ph
    where ph.person_id = pe.id and ph.archived_at is null
  )
order by po.policy_number nulls last,
         -- Main member first within each policy: they are the one the office
         -- actually rings, and the one most likely to know the others' numbers.
         (pm.member_type = 'main_member') desc,
         pe.surname, pe.first_names;
