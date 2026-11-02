-- 0014 - Close Supabase's Data API to signed-in accounts.
--
-- 0004 and 0008-0013 gave Supabase's `authenticated` role read access (and
-- some update access) to the enquiry and member-book tables. That was for a
-- portal that would read through Supabase's Data API. It no longer does: every
-- read and write now goes through our API, which logs in as `induduzo_api` and
-- checks the staff list and the role on every request.
--
-- Left in place, those grants let any Supabase account bypass all of that and
-- read or edit members straight from the Data API, including ID numbers.
-- Public sign-up was switched off on 16 Oct 2026, and this removes the access
-- itself.
--
-- After this, `authenticated` has no policy and no privilege on these tables.
-- RLS stays on, so the Data API returns nothing to a signed-in account.
-- `anon` is untouched: it keeps only what 0004 gave it.
--
-- Safe to re-run, and portable. On Supabase, 0013's tables do not exist yet,
-- so each one is checked before it is touched.

do $$
declare
  item record;
begin
  for item in
    select * from (values
      ('plan_enquiries',      'staff_can_read_enquiries'),
      ('plan_enquiries',      'staff_can_update_enquiries'),
      ('enquiry_events',      'staff_can_read_events'),
      ('ref_member_types',    'staff_read_member_types'),
      ('ref_policy_statuses', 'staff_read_policy_statuses'),
      ('ref_plans',           'staff_read_plans'),
      ('ref_branches',        'staff_read_branches'),
      ('ref_benefit_types',   'staff_read_benefit_types'),
      ('people',              'staff_read_people'),
      ('people',              'staff_write_people'),
      ('person_phones',       'staff_read_phones'),
      ('person_phones',       'staff_write_phones'),
      ('addresses',           'staff_read_addresses'),
      ('addresses',           'staff_write_addresses'),
      ('policies',            'staff_read_policies'),
      ('policies',            'staff_write_policies'),
      ('policy_members',      'staff_read_members'),
      ('policy_members',      'staff_write_members'),
      ('policy_benefits',     'staff_read_benefits'),
      ('policy_links',        'staff_read_links'),
      ('policy_payments',     'staff_read_payments'),
      ('data_quality_flags',  'staff_read_flags'),
      ('data_quality_flags',  'staff_write_flags'),
      ('premium_instalments', 'staff_read_instalments'),
      ('payment_reminders',   'staff_read_reminders')
    ) as p(table_name, policy_name)
  loop
    if to_regclass('public.' || item.table_name) is not null then
      execute format('drop policy if exists %I on public.%I',
                     item.policy_name, item.table_name);
    end if;
  end loop;

  -- Privileges too, not only policies. If RLS were ever switched off on one of
  -- these tables, a privilege with no policy behind it would reopen the door.
  for item in
    select unnest(array[
      'plan_enquiries', 'enquiry_events',
      'ref_member_types', 'ref_policy_statuses', 'ref_plans',
      'ref_branches', 'ref_benefit_types',
      'people', 'person_phones', 'addresses',
      'policies', 'policy_members', 'policy_benefits',
      'policy_links', 'policy_payments', 'policy_overview',
      'data_quality_flags',
      'premium_instalments', 'payment_reminders', 'instalments_outstanding'
    ]) as table_name
  loop
    if to_regclass('public.' || item.table_name) is not null then
      execute format('revoke all on public.%I from authenticated', item.table_name);
    end if;
  end loop;
end
$$;
