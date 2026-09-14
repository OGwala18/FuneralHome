-- 0012 - Covering indexes for the foreign keys added in 0010 and 0011.
--
-- WHY THIS EXISTS
-- Postgres indexes the TARGET of a foreign key automatically (it has to: that
-- is the primary key) but never the SOURCE column. Two things then get slower
-- as the book of business grows:
--
--   1. The obvious direction. "Every policy on Plan A", "every life whose role
--      is still unrecorded" - ordinary reporting queries that would otherwise
--      scan the whole table.
--   2. The one that surprises people. Deleting or updating a referenced row
--      makes Postgres check every child table for dependents, and with no
--      index that check is a sequential scan. Retiring one product could lock
--      the policies table for as long as it takes to read all of it.
--
-- These are all small B-trees on low-cardinality columns and cost almost
-- nothing to maintain at this scale. Supabase's database linter flags every
-- one of them; this file is the answer to that report.

-- The office's correction queue joins flags back to the membership row.
create index data_quality_flags_member_idx
  on data_quality_flags (policy_member_id)
  where policy_member_id is not null;

-- "Which lives still have no role recorded?" - the actual clean-up workflow
-- after the first import, where 50 of 61 rows are 'unspecified'.
create index policy_members_type_idx on policy_members (member_type)
  where archived_at is null;

-- Product and branch reporting, and safe retirement of a ref_plans row.
create index policies_plan_idx on policies (plan_code)
  where plan_code is not null and archived_at is null;
create index policies_branch_idx on policies (branch_code)
  where branch_code is not null and archived_at is null;

-- Benefits are empty today. Indexed anyway because people are deleted under
-- `on delete restrict`, and that check reads this table every time.
create index policy_benefits_person_idx on policy_benefits (person_id)
  where person_id is not null and archived_at is null;
create index policy_benefits_type_idx on policy_benefits (benefit_code)
  where archived_at is null;
