-- 0021 - Cover is set by the plan, like the premium.
--
-- WHY THIS EXISTS
-- The owner, 11 Nov 2026: once a plan is chosen, its premium and its cover
-- amount are fixed. 0020 took the premium out of staff hands; the cover was
-- still typed in at enrolment, so two families on the same plan could be
-- recorded with different cover by accident.
--
-- HOW
-- Each line of the price list carries its cover. Enrolment copies both the
-- premium and the cover from the line the policy is sold on, and the API no
-- longer accepts a cover typed in. A policy keeps its OWN cover_cents, so a
-- later change to the list never rewrites an existing family's cover.
--
-- THE AMOUNTS ARE NOT HERE YET
-- They are the owner's to give. Until a line has one, a policy sold on it is
-- recorded with no cover amount (null), never a guessed one. The amounts go in
-- a later migration as plain UPDATEs of ref_plan_prices.cover_cents.
--
-- WHERE IT RUNS
-- Wherever 0020 has run. Not Supabase until the API's own database there is
-- settled (as 0013 and 0016).

alter table ref_plan_prices
  add column if not exists cover_cents bigint
    check (cover_cents is null or cover_cents >= 0);

comment on column ref_plan_prices.cover_cents is
  'The cover a policy sold on this line receives, in cents. Copied to policies.cover_cents at enrolment. Null: not on record yet.';
