# Hosting decision

Recommendation for taking Induduzo live, written against the real constraints:
~R1,000/month budget, 500 policyholders growing to 3,000, five staff,
~R200,000/month flowing through the system, and downtime meaning missed premium
collections.

**The short version: Supabase Pro for data and auth, Railway for the API,
Netlify for the two front ends, Cloudflare in front. About R620/month.**

---

## Recommended stack

| Layer | Where | Monthly |
|---|---|---|
| Website + staff portal | Netlify free | R0 |
| API (FastAPI) | Railway, EU West | ~$5–10 (R90–180) |
| Postgres + Auth + backups | Supabase Pro | $25 (R450) |
| DNS, CDN, WAF | Cloudflare free | R0 |
| Uptime monitoring | UptimeRobot free | R0 |
| | **Total** | **~R540–630** |

That leaves roughly R400/month of headroom inside the budget for the
point-in-time-recovery add-on or a larger API instance as the book grows.

---

## Why this rather than the alternatives

### Why not Railway Postgres, when Railway is already hosting the API?

Because you are paying for Supabase anyway, and Supabase Pro includes the
database. Using Railway Postgres means **$25/month for authentication alone**,
plus a second database to back up, monitor and keep alive. Same money, more
moving parts, and you own the backup problem.

### Why Supabase must be on the paid plan

This is not optional in your situation. **The free tier pauses a project after
seven days of low activity.** You are using Supabase for staff sign-in, so a
quiet week means nobody can log in. Paid projects are never paused. Pro also
brings daily backups with 7-day retention, which matters for financial records
under POPIA.

### Why not Cloudflare for the application

Cloudflare Workers is excellent, but it is a JavaScript runtime. The API is
Python/FastAPI, so moving it there means a rewrite, and Workers' database story
(D1) is SQLite, not Postgres. **Use Cloudflare for what it is genuinely best at**
— DNS, CDN, DDoS protection and a WAF sitting in front of Netlify and Railway.
That part is free and worth doing.

### Why not a cheap VPS (Hetzner, DigitalOcean)

€4/month looks attractive until you are the one patching the OS, renewing
certificates, configuring backups and being paged at 2am. For a system where
downtime costs premium collections and there is no ops team, managed hosting is
the cheaper option once your time is priced in.

---

## Region: everything in EU West

Railway has four regions — US West, US East, EU West (Amsterdam) and Southeast
Asia. **There is no African region**, and Supabase does not offer `af-south-1`
either; they have declined it for operational reasons. EU West is the closest
option to Pietermaritzburg at roughly 150–180ms.

**The important rule is that the API and the database sit in the same region.**
User-to-API latency is paid once per request; API-to-database latency is paid on
*every query* within that request. Splitting them across continents is the
single easiest way to make this system feel slow.

Cloudflare's CDN removes most of the distance penalty for the website, because
the static assets are served from a Johannesburg edge node regardless.

---

## Scale reality check

3,000 policyholders and five staff is a **small** dataset — a few thousand rows.
Nothing here is a scale problem. The engineering risk is not throughput, it is:

1. **Availability.** One API container is a single point of failure.
2. **Backups.** Financial and personal records under POPIA.
3. **Knowing when it breaks.** Downtime nobody notices is downtime that lasts
   all weekend.

Which is why the recommendation spends money on managed backups and monitoring
rather than on capacity you will not use.

---

## Before going live

1. **Run the migrations.** `python db/migrate.py` against the production
   `DATABASE_URL`. Nothing works without this, and managed Postgres will not do
   it for you. If the schema already exists, adopt it with
   `--baseline 0005_api_role.sql` first.
2. **Set the API role password out of band.** `0005_api_role.sql` creates
   `induduzo_api` as NOLOGIN on purpose; a credential must never live in
   migration history:
   `alter role induduzo_api login password '<from your secret store>';`
3. **Set `ENVIRONMENT=production`.** This is what disables `/docs` and turns on
   HSTS. Verified: without it, `/docs` returns 200.
4. **Set `CORS_ORIGINS`** to the real origins, e.g.
   `https://induduzo.co.za,https://portal.induduzo.co.za`.
5. **Turn off Supabase public sign-up** and confirm daily backups are on.
6. **Add uptime monitoring** on `/health` with SMS or email alerts. Free, and
   the difference between five minutes of downtime and a lost weekend.
7. **Restore a backup once, on purpose,** before you need to. An untested backup
   is a hope, not a plan.

---

## What this does not solve

Taking payments still requires FSCA licensing and an underwriter — see
`Induduzo - Taking Payments Online.docx`. Hosting is not the blocker there.
Capturing enquiries, which is what this system does today, is unaffected.

---

## Revision — 14 September 2026

The recommendation above stands as written. Two things have changed in
practice, and one risk it identified is now live rather than hypothetical.

### Railway, current published rates

Checked against Railway's own pricing documentation, so this does not have to be
researched a third time:

| | |
|---|---|
| Hobby | **$5/month**, including $5 of resource usage |
| Pro | **$20/month**, including $20 of resource usage |
| RAM | **$10** / GB / month |
| vCPU | **$20** / vCPU / month |
| Network egress | **$0.05** / GB |
| Volume storage | **$0.15** / GB / month |

Included usage **resets monthly and does not roll over**. Resources bill
per-minute against actual consumption, not against what is allocated, so a
low-traffic FastAPI service sits comfortably inside Hobby's included $5. The
~R90–180 estimate in the table above is still the right number to budget.

The region picture has not changed: EU West (Amsterdam) remains the closest
option and there is still no African region.

### Supabase is on the free tier, not Pro

Contrary to the stack table above, the project has been running on the **free**
plan. The table's R450 line has never been a real cost, and the expenses sheet
that inherited it was overstating the monthly total by that amount.

The decision, taken deliberately on 14 September 2026, is to **stay on free**.
Free allows 50,000 monthly active users against a real staff population of
under ten, so the user limit was never the binding constraint.

The pause risk this document raised is real and is now mitigated in code rather
than by paying: `db/keepalive.py` touches the database and is designed to be run
on a schedule. **Until something actually runs it on a clock, a human must run
it — or simply open the Supabase dashboard — at least weekly.**

### The part the keep-alive does not solve

The argument for Pro above rested on two legs, and only one of them has been
answered. Pausing is handled. **Backups are not.**

The free tier has no automated daily backups. There are now 61 real members and
their dependants in this database, carrying ID numbers and dates of birth, and
the original argument for Pro cited daily backups with 7-day retention as
mattering "for financial records under POPIA". That reasoning did not stop being
true when the plan changed.

So this is an accepted, temporary risk rather than a solved problem. Either
upgrade to Pro before the book grows, or add a scheduled `pg_dump` to somewhere
off-platform. It should not stay unresolved for long.
