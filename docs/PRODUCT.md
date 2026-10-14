# PRODUCT.md — Induduzo staff portal

register: product

## What this is

An internal tool for the Induduzo Funeral Home office in Pietermaritzburg. It is
the staff side of `induduzo.co.za`: the public site captures enquiries, this
portal is where the office works them.

Design serves the work here. Nobody chooses this product, nobody is being sold
to, and nobody should notice the interface. The measure is whether Nandi gets
through the call list before lunch.

## Users

**Office staff, one to five people, on desktop.** They are not power users and
they are not technophobes. They spend the day on the phone to families who have
recently been bereaved or are worried about what happens when they die. The
person on the other end of the call is often distressed.

The primary user is on a 1440px screen in a small office. Occasionally the same
person checks the queue on a phone between appointments, which is why three
mobile screens exist and the rest do not.

Roles are `viewer`, `admin` and `owner`. Only `owner` manages staff.

## Product purpose

Turn a list of enquiries into conversations that actually happen, and keep a
clear record of what was said, so the next call starts where the last one ended.

## Tone

Calm, plain, and never chirpy. This is software used beside grief. It should
feel like a well-kept ledger, not a growth dashboard.

- Say what happened: "This call has not been saved."
- Never celebrate: no confetti, no "Great job!", no exclamation marks.
- Never use euphemism for death, and never use jargon for it either.
- People have names. "Sibusiso Ndlovu", not "Lead #1408".

## Anti-references

- **CRM dashboards.** Pipelines, deal values, leaderboards, win rates. A family
  is not a deal and the office is not a sales floor.
- **Growth-SaaS chrome.** Hero metrics with big gradient numbers, sparklines
  everywhere, "streaks", gamification of any kind.
- **Dense enterprise admin.** Twelve-column tables of raw database fields with
  no hierarchy, where every row looks identical and nothing is prioritised.
- **Consumer app playfulness.** Rounded pastel illustrations, mascots, playful
  microcopy. Wrong register entirely for the subject matter.

## Strategic principles

The design laws the Figma work was built against. They are the acceptance
criteria for this front end, not decoration.

**Reduce what has to be decided**
- *Hick* — few choices per screen. Four destinations, not twelve.
- *Occam* — one pattern for a job, used everywhere. A record looks like a record.
- *Pragnanz* — simplify. If a screen needs a legend, it is wrong.
- *Pareto* — reveal complexity gradually. The common 20% is on the surface.

**Make the next action obvious and cheap to hit**
- *Von Restorff* — exactly one primary action per moment, and it looks unlike
  everything else on screen.
- *Fitts* — 48px minimum targets.
- *Minimize target distance* — the action sits next to the thing it acts on.
- *Serial position* — the most important item is first, the next-best is last.

**Respect what people already know**
- *Jakob* — familiar patterns. A table sorts by clicking its header.
- *Similarity* — sensible defaults, so the common case needs no input.

**Group so the eye does the work**
- *Proximity* — related facts sit together, separated by space not by lines.
- *Uniform connectedness* — things that belong share a surface.
- *Miller* — chunk. A queue of 13 is five groups, not a list of thirteen.

**Keep the work moving**
- *Doherty* — under 400ms, or show that something is happening.
- *Zeigarnik* — visible progress. "4 of 13 conversations handled."
- *Tesler* — the irreducible complexity lives in the software, not the user.

**Be forgiving**
- *Postel* — accept messy input, prevent the error before it happens.
- *Parkinson* — every outcome is recoverable. Undo, not "are you sure".
- *Peak-End* — end a flow on something reassuring, never a dead end.

## Constraints that outrank aesthetics

1. **The portal is a separate app** from the public site and always will be.
   No admin code in the public bundle.
2. **Plain CSS, no Tailwind.** A deliberate call recorded in ARCHITECTURE.md.
3. **Colours come from tokens** in `portal/src/index.css`. Light only. No dark
   mode, no theme switch.
4. **Personal data never goes into logs.** References, not names.
5. The UI gate is a convenience. The **API is the security boundary** and
   re-checks the role on every request.
