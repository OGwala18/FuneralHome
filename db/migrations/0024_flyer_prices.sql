-- 0024 - The price list as the owner's flyer has it (12 Nov 2026).
--
-- The flyer is the source of truth for plan prices. Against 0020's list:
--
--   DOME PLAN. Two monthly options, not a single R400 once-off price:
--     Option 1, husband & wife  R500 a month
--     Option 2, family, up to 15  R750 a month
--   The R400 on the flyer is the once-off joining fee for dome and casket
--   plans, not the Dome premium. The old once-off line is retired (kept, made
--   inactive, so a policy sold on it still traces back to a line).
--
--   COVER. The flyer states the payout per life by age: R1,000 under 21 and
--   R2,000 at 21 and over. Every plan's main member is 21 or over, so each line
--   carries R2,000, the main member's payout. A policy keeps its own copy, as
--   0021 explains.
--
--   Plans A, B and C are unchanged. The flyer prints Plan C couple, flat lid,
--   46-59 as R60, below the R100 for 21-45; that looks like a misprint and the
--   R200 from 0020 stays until the owner confirms it.

update ref_plan_prices
   set is_active = false
 where plan_code = 'dome_plan' and option_code = 'once_off';

insert into ref_plan_prices
  (plan_code, option_code, option_label, min_age, max_age, premium_cents, billing, sort_order)
values
  ('dome_plan', 'husband_wife', 'Dome Option 1: husband & wife', null, null, 50000, 'monthly', 41),
  ('dome_plan', 'family',       'Dome Option 2: family, up to 15', null, null, 75000, 'monthly', 42);

update ref_plan_prices set cover_cents = 200000 where is_active;
