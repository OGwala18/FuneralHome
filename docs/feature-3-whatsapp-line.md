# Feature 3 — One WhatsApp line that sends, receives and answers

**Working brief for whoever builds this, including an agent picking it up cold.**
Read `ARCHITECTURE.md` and `docs/twilio-setup.md` first.

| | |
|---|---|
| Status | Planned. The line is registered with Twilio and online (20 Oct 2026). Nothing is built in the API yet |
| Repo state at time of writing | `Dev` at `9178d14`, 21 Oct 2026 |
| Touches | `backend/`, `db/migrations/`, later `portal/` and `frontend/src/lib/contact.ts` |

---

## 1. What this is

Induduzo's WhatsApp line is **073 731 0521** (+27 73 731 0521). It replaced
069 706 0387 on 20 Oct 2026 (migration 0017). It is a Twilio WhatsApp sender,
display name "Induduzo": an API line, not a phone. The owner's goal, for
transparency and trust, is that **the number that sends a family their
confirmation is the same number they can message back**, that nothing sent to it
is lost, and that **every message gets an immediate, useful answer, day or
night**.

So the line will:

1. **Send** the registration confirmation, as today.
2. **Receive** every message a family sends, and store it in our database,
   linked to their enquiry or member record when the number matches.
3. **Answer** with an automatic menu (§5). Rules only, no AI: a family picks
   numbered options and gets a fixed answer, a callback, or a short registration.
4. **Hand over** to staff: callback requests, new leads and anything the menu
   can't answer reach admin@induduzo.co.za and, later, a portal inbox.
5. Later, let **staff reply from the portal**, from the same number.

Once this works on the real number, the website's "WhatsApp us" button moves from
079 751 0648 to 073 731 0521. Until then the button stays where it is, because
without this feature, messages to the line reach nobody.

---

## 2. Decisions taken

| Decision | Choice | Who, when |
|---|---|---|
| Photos and documents | **Attached to the forwarded email**, then **Twilio's copy is deleted** so documents don't stay with a third party. Size cap; anything too large is noted in the email and left in Twilio | Owner, 19 Oct 2026 |
| Staff replies | **Yes, from the portal**, as a later phase | Owner, 19 Oct 2026 |
| Forwarded to | **admin@induduzo.co.za** | Owner, 19 Oct 2026 |
| Website button | **Stays on 079 751 0648** until this works on the real number | Owner, 19 Oct 2026 |
| The line | **073 731 0521**. 069 706 0387 is retired | Owner, 20 Oct 2026 |
| Automatic replies | **A rule-based menu (§5) replaces the single acknowledgement.** No AI for Induduzo | Owner, 21 Oct 2026 |
| The menu | **The seven options in §5, as drafted** | Owner, 21 Oct 2026 |
| Family details over WhatsApp | **Names, relationships and dates of birth only.** ID numbers are confirmed on the liaison call, so they never sit in WhatsApp chats or Twilio's logs | Owner, 21 Oct 2026 |
| Language | **English first, isiZulu next** (Bit M5) | Owner, 21 Oct 2026 |
| Office hours | **Mon–Fri 08:00–17:00, Sat 08:00–13:00** (South African time). Sundays and public holidays are closed | Owner, 21 Oct 2026 |

## 3. Still open

| # | Question | Recommendation | Needed by |
|---|---|---|---|
| 1 | How long messages are kept (POPIA: no longer than needed) | 24 months, then deleted by a job; the same for every message | Before production |
| 2 | The isiZulu wording of every menu message | Written once the English is settled, then checked by a first-language speaker on staff | M5 |
| 3 | Public holidays | A short list in the menu content, updated yearly. On those days callbacks are promised for the next working day | M2 |
| 4 | What option 4 (paying) says about banking details | **No account numbers on WhatsApp.** Scammers copy them. The answer lists the ways to pay, and a staff member confirms the details on the call | M1 |

---

## 4. How it works

```
 Family's WhatsApp ──▶ Twilio (073 731 0521) ──▶ POST /api/whatsapp/inbound
                                                   1. check X-Twilio-Signature (reject if wrong)
                                                   2. store the message (once per Twilio MessageSid)
                                                   3. match the number to an enquiry or member
                                                   4. run the menu: read the conversation's state,
                                                      choose the reply, save the new state
                                                   5. reply in the response (TwiML), within a second or two
                                                        │ after the response, in the background
                                                        ▼
                                                   6. if the step needs staff (callback, new lead,
                                                      free text): email admin@
                                                   7. download any attachments, email them, then
                                                      delete Twilio's copy

 Registration confirmation ──▶ Twilio ──▶ family
            │ stored as an outbound message
            └──── Twilio status callback ──▶ POST /api/whatsapp/status
                                             queued → sent → delivered → read (or failed)
```

- **Store first, then reply.** This follows the same rule as leads: a mail
  failure or a menu bug must never lose the message. Twilio does not retry a
  webhook that fails, so the endpoint stores the message and returns quickly.
- **Menu replies need no template.** A family who messages the line opens a
  24-hour window. Replies inside it are ordinary messages, so they need no Meta
  approval. Only messages Induduzo starts, like the confirmation, need an approved
  template.
- **Safety net (W5).** An hourly job asks Twilio's API for recent inbound
  messages and adds any the webhook missed, for example while the API was
  restarting. It also re-sends forwards that failed.

---

## 5. The menu

### 5.1 The first message

Any message from a number with no conversation open (or after 30 minutes'
silence) gets the greeting and the main menu:

> Sawubona 🙏 Welcome to Induduzo Funeral Home. Reply with a number:
> 1. Someone has passed away
> 2. Our plans and prices
> 3. Join a plan
> 4. Paying my premium
> 5. My policy / adding family members
> 6. Branches, hours and contact
> 7. Talk to a person

### 5.2 What each option does

| Option | What happens |
|---|---|
| **1. Someone has passed away** | Answers straight away, day or night, before anything else: condolences, the 24-hour numbers (079 751 0648 / 082 954 9241), and "Reply 1 and we'll call you now". A reply of 1 creates an **urgent** callback and emails admin@ at once. A grieving family must never be stuck in a menu |
| **2. Our plans and prices** | A sub-menu: Plan A, Plan B, Plan C, Dome Plan, Compare. Each answer gives the price, who is covered and what's included, and ends with "Reply 1 to join this plan, 0 for the menu" |
| **3. Join a plan** | The registration in §5.4 |
| **4. Paying my premium** | How to pay (debit order, EFT, cash at a branch, card), with no account numbers (open decision 4). Anything about a specific account becomes a callback, because a phone number alone doesn't prove who someone is |
| **5. My policy / adding family members** | A callback, for the same reason. Adding family members to a **new** registration is §5.5 |
| **6. Branches, hours and contact** | Address, office hours, phone numbers and a map link |
| **7. Talk to a person** | A callback (§5.3) |

After every answer: *"Did this help? 1 Yes, 2 No"*. **Yes** asks for a rating
from 1 to 5 and an optional comment. **No** offers a callback.

### 5.3 Callbacks and office hours

- A callback request is stored, linked to the family's enquiry or member record
  when the number matches, and emailed to admin@.
- **In office hours** the reply says *"Thank you. Someone will call you shortly
  on this number."*
- **Outside them** it says *"Thank you. The office is closed now; someone will
  call you when it opens at 08:00 on <day>."* Bereavement (option 1) is the
  exception: it always gives the 24-hour numbers too.
- Office hours are Mon–Fri 08:00–17:00 and Sat 08:00–13:00, South African time,
  kept in the menu content with the public holidays.

### 5.4 Joining a plan over WhatsApp

1. *"What is your first name?"*, then *"And your surname?"*
2. *"Which plan?"*, with the plan list and "Not sure yet".
3. Consent: *"May Induduzo Funeral Home contact you about funeral cover on this
   number? Reply YES to agree."* Nothing is saved as a lead without YES.
4. The API creates the same stage-1 lead the website does:
   - the mobile number is the WhatsApp number itself;
   - `contact_consent` is true and marketing consent stays false;
   - `how_heard` is "WhatsApp".

   It sends the same office email and replies with the reference: *"Thank you,
   Thandiwe. Your reference is IND-2026-001234. A family liaison will call you
   within one working day."*
5. It then offers §5.5: *"Would you like to tell us who else to cover? 1 Yes,
   2 Not now"*.

### 5.5 Family details over WhatsApp

For each person, one question at a time:
- name;
- relationship (spouse, child, parent, extended family, beneficiary);
- date of birth.

Then *"Add another person? 1 Yes, 2 No, that's everyone"*.

- **Never ID numbers** (decision of 21 Oct). If someone types a 13-digit number,
  the reply asks them not to send ID numbers here, and the number is not stored.
  The liaison confirms ID numbers on the call.
- The people are stored against the enquiry for staff to check on the call. They
  are **not** turned into policy members automatically: enrolment stays a staff
  action in the portal.

### 5.6 Everywhere in the menu

- **0** or **menu** goes back to the main menu.
- **STOP** switches off automated messages for that number. Messages are still
  stored and forwarded, and **START** switches them back on.
- A reply the menu doesn't understand gets *"Sorry, please reply with a number
  from the list, or 7 to talk to a person."* After two in a row it offers a
  callback.
- Free text the menu can't use (anything that isn't an option, a name or a date
  it asked for) is forwarded to admin@, so a real question is never lost.
- A conversation left for **30 minutes** starts again from the greeting.

### 5.7 The menu is data

The wording, the menu tree, the office hours and the public holidays live in one
content file in `backend/app/` (Bit M1), not scattered through code:
- changing an answer is a text edit and a pull request;
- adding isiZulu (M5) is a second copy of the text.

**Plans and prices** in that file must match `frontend/src/data/plans.ts`, the
single source of truth for plans (ARCHITECTURE.md). The API image doesn't contain
`frontend/`, so it can't read that file at run time. Instead, a test reads
`plans.ts` and fails if the menu's plan names or prices drift from it.

---

## 6. Data model

One migration per bit, with the next free number. They follow the house style:
- `tenant_id` on every row;
- RLS on, with a policy for `induduzo_api` only;
- nothing for `anon` or `authenticated` (SECURITY.md rule 8).

Sketches, not final SQL:

```sql
-- W2. Every message, both ways.
create table whatsapp_messages (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null default '00000000-0000-0000-0000-000000000001',
  direction        text not null check (direction in ('inbound', 'outbound')),
  twilio_sid       text not null unique,          -- MessageSid: makes storing idempotent
  business_number  text not null,                 -- +27737310521
  other_number     text not null,                 -- the family's number, E.164
  profile_name     text,                          -- WhatsApp display name (inbound)
  body             text,
  media            jsonb not null default '[]',   -- [{content_type, bytes, forwarded, deleted}]; no URLs
  status           text not null,                 -- inbound: received|forwarded|forward_failed
                                                  -- outbound: queued|sent|delivered|read|failed|undelivered
  error_code       text,
  enquiry_id       uuid references plan_enquiries(id),
  person_id        uuid references people(id),
  forwarded_at     timestamptz,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
-- indexes: (other_number, created_at desc) for conversations; (status) where not final

-- M1. Where each number is in the menu.
create table whatsapp_conversations (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null default '00000000-0000-0000-0000-000000000001',
  other_number     text not null,                 -- unique while the conversation is open
  state            text not null,                 -- a node id in the menu content, e.g. 'main', 'plans', 'join.surname'
  data             jsonb not null default '{}',   -- answers gathered so far (first name, plan); never an ID number
  misses           smallint not null default 0,   -- replies in a row the menu didn't understand
  opted_out_at     timestamptz,                   -- STOP
  last_message_at  timestamptz not null,          -- a gap of 30 minutes restarts the menu
  enquiry_id       uuid references plan_enquiries(id),
  created_at       timestamptz not null default now()
);

-- M2. Callbacks for staff, and ratings.
create table whatsapp_callbacks (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null default '00000000-0000-0000-0000-000000000001',
  other_number     text not null,
  reason           text not null check (reason in
                     ('bereavement', 'payment', 'policy', 'talk_to_person', 'not_helped', 'misunderstood')),
  urgent           boolean not null default false,
  enquiry_id       uuid references plan_enquiries(id),
  person_id        uuid references people(id),
  requested_at     timestamptz not null default now(),
  promised_for     timestamptz,                   -- "when the office opens"
  done_at          timestamptz,
  done_by          text
);

create table whatsapp_feedback (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null default '00000000-0000-0000-0000-000000000001',
  other_number     text not null,
  topic            text not null,                 -- the menu node that was answered
  helped           boolean not null,
  rating           smallint check (rating between 1 and 5),
  comment          text,
  created_at       timestamptz not null default now()
);

-- M4. People a family named over WhatsApp. Not policy members: staff check them on the call.
create table enquiry_family_members (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null default '00000000-0000-0000-0000-000000000001',
  enquiry_id       uuid not null references plan_enquiries(id),
  full_name        text not null,
  relationship     text not null check (relationship in
                     ('spouse', 'child', 'parent', 'extended_family', 'beneficiary')),
  date_of_birth    date,
  source           text not null default 'whatsapp',
  created_at       timestamptz not null default now()
  -- deliberately no ID number column
);
```

The existing `plan_enquiries.whatsapp_message_sid` stays. The confirmation is
also written to `whatsapp_messages`, so one table holds every message both ways.

---

## 7. Settings

| Variable | What |
|---|---|
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`, `TWILIO_CONTENT_SID` | As today. The auth token also signs the webhooks. Sealed, pasted by the owner. Internal has all four since 20 Oct 2026 |
| `PUBLIC_API_URL` | The API's public address, e.g. `https://api-internal-8e41.up.railway.app`. Behind Railway's proxy the request URL is not the one Twilio signed, so the signature check uses this |
| `WHATSAPP_OUTBOUND` | `off` / `allowlist` / `on`. **Internal uses `allowlist`.** Confirmations **and menu replies** then go only to the numbers in `WHATSAPP_TEST_RECIPIENTS` (staff phones), so tests never message a real family. **Production uses `on`.** This replaces "WhatsApp is on when the credentials exist" |
| `WHATSAPP_TEST_RECIPIENTS` | Comma-separated E.164 numbers, internal only |
| `WHATSAPP_FORWARD_TO` | Defaults to `MAIL_TO` (admin@induduzo.co.za) |

The menu's content, office hours and holidays are in the content file (§5.7),
not in settings.

---

## 8. Rules

- **Every webhook is signature-checked.** No valid `X-Twilio-Signature` means
  403. If `TWILIO_AUTH_TOKEN` is missing, the endpoint returns 503 rather than
  accepting unsigned calls.
- **No message text or numbers in logs.** Log the `MessageSid` and the menu
  state only (ARCHITECTURE.md rule 9). Two existing leaks are fixed in W1:
  - the send-failure log line writes Twilio's exception text, which can contain
    the number;
  - the Twilio library logs every request it makes at INFO, including the
    account id. Set its logger (`twilio.http_client`) to WARNING.
- **What is forwarded to admin@:** new leads, callback requests, free text the
  menu couldn't use, and attachments. Not menu taps like "2", which would flood
  the inbox; those are in the portal inbox (W9).
- **Email subject:** "WhatsApp from <name or number>". It carries personal data,
  so it is never logged, the same rule as the lead emails.
- **Attachments:** the API downloads them with the account credentials. They
  are attached up to a total of 15 MB per email. Anything larger is listed but
  not attached and not deleted. Twilio's copy of a file is deleted only after the
  email that carries it is accepted by the mail server.
- **Never an ID number** in a stored conversation, a log or an email from the
  menu (§5.5).
- **Replies from staff (W10):** a free-text reply is allowed within 24 hours of
  the family's last message. Outside that window only an approved template can
  be sent, so the portal says so.
- **Cost:** every message is billed, both ways. A Twilio fee per message, plus
  Meta's per-message charge on replies since 1 Oct 2026. A 6–10 message
  conversation is roughly R1–R2. Keep answers to one message where possible.

---

## 9. Testing

**API behaviour tests**, on every pull request:
- **Signatures:** requests are signed with a test auth token, using the same
  algorithm as Twilio:
  - a valid signature is accepted;
  - a wrong signature, a missing signature or a changed body gets 403;
  - with no token configured, the endpoint returns 503.
- **Storing:** the same `MessageSid` twice gives one row, one reply and at most
  one email.
- **Matching:** a number that matches an enquiry or a member links the row. An
  unknown number is still stored and answered.
- **The menu**, driven by a table of messages in and replies out:
  - the greeting on a first message and after 30 minutes' silence;
  - every option and sub-option reaches its answer;
  - **option 1 always answers first**, with the 24-hour numbers, whatever state
    the conversation was in;
  - 0 and "menu" go back; two misunderstood replies offer a callback;
  - STOP stops replies but still stores and forwards; START resumes;
  - callbacks promise the right time in and out of office hours, including
    Saturday afternoon, Sunday and a public holiday;
  - joining creates a lead **only after YES**, sends the office email and replies
    with the reference;
  - family details are stored; a 13-digit number is refused and not stored;
  - ratings and comments are stored.
- **Plans:** the menu's plan names and prices match `frontend/src/data/plans.ts`.
- **Outbound and status callbacks:**
  - the confirmation is stored;
  - status callbacks move it from sent to delivered, read or failed;
  - with `allowlist`, a number not on the list is never sent to, menu replies
    included.
- **Logs and audit:** no message body or phone number appears in captured logs.

**On internal, with the real line (W6).** The line has been registered and
online since 20 Oct, so the sandbox isn't needed:
1. Point the sender's "incoming messages" webhook and status callback at
   internal, and set `WHATSAPP_OUTBOUND=allowlist` with the owner's number.
2. From the owner's phone, walk every menu path: each answer arrives, callbacks
   and leads reach admin@, a photo arrives by email and Twilio's copy is gone.
3. A message from a number not on the allowlist is stored and gets no reply.
4. A test enquiry from the website gets a confirmation that shows as delivered,
   then read (once Meta approves the template).

---

## 10. Build order: one bit per session

Use the same way of working as `docs/feature-2-staff-two-factor.md` §12: a fresh
session per bit, a branch from `Dev`, one pull request, and the tracker row
updated in that pull request.

| Bit | What | Depends on | Size (tokens) | Status |
|---|---|---|---|---|
| W1 | Outbound switch with the internal allowlist; `PUBLIC_API_URL`; stop the two log leaks (§8) | — | ~4M | Not started |
| W2 | `whatsapp_messages` table; store outbound confirmations; signed status-callback endpoint | W1 | ~8M | Not started |
| W3 | Inbound webhook: signature, store, match, reply with a placeholder greeting | W2 | ~8M | Not started |
| M1 | Menu engine and content file: greeting, the seven options, plan answers, branches and hours, 0/menu, misunderstood replies, 30-minute restart; the plans test | W3 | ~12M | Not started |
| M2 | Callbacks with office hours and holidays, "Did this help?", ratings, STOP/START | M1 | ~10M | Not started |
| M3 | Join over WhatsApp: consent, lead, office email, reference reply | M2 | ~8M | Not started |
| M4 | Family details over WhatsApp (no ID numbers) | M3 | ~8M | Not started |
| W4 | Forward to admin@ (leads, callbacks, free text, attachments); delete Twilio's copy | M2 | ~10M | Not started |
| W5 | Safety net: hourly backfill of missed messages and re-send of failed forwards | W4 | ~6M | Not started |
| W6 | Point the webhooks at internal and prove every path with the real line (§9) | W4, M4 | ~6M | Not started |
| W8 | Move the website's WhatsApp button to 073 731 0521 | W6, production API | ~3M | Not started |
| W9 | Portal: Messages inbox and the callback queue, linked to enquiries and members | W4 | ~12M | Not started |
| W10 | Replies from the portal (24-hour window; template outside it) | W9 | ~12M | Not started |
| M5 | isiZulu: language choice on the greeting, and the whole menu in isiZulu (open decision 2) | M4 | ~8M | Not started |
| — | Retention job (open decision 1) | W4 | ~3M | Not started |

The old W7, registering the number, was done by hand on 20 Oct 2026; see
`docs/twilio-setup.md`.

**Starting a bit:** paste this into a new session, with the bit filled in:

> Build **Bit Xn** of `docs/feature-3-whatsapp-line.md` (§10). Read `CLAUDE.md`,
> `ARCHITECTURE.md`, `docs/twilio-setup.md` and the plan first. Branch from `Dev`
> as `feat/whatsapp-xn-<short-name>`. Stay inside the bit's scope. Never send a
> real WhatsApp to anyone but the allowlisted test numbers, and never handle the
> Twilio auth token, which the owner pastes into Railway. When the bit's tests
> pass, update its tracker row and open the pull request into `Dev`.

---

## 11. Risks

| Risk | Handled by |
|---|---|
| API down when a message arrives | Twilio doesn't retry; the hourly backfill (W5) catches it, and the menu answers the next message |
| A bereaved family meets a menu | Option 1 is first, answers immediately with the 24-hour numbers, and offers an urgent callback |
| Email fails | The message is already stored; marked `forward_failed`; re-sent by W5 |
| Forged webhook calls | Signature check against the auth token; 403 otherwise |
| A test messages a real family | `WHATSAPP_OUTBOUND=allowlist` on internal, for menu replies too |
| ID numbers end up in chats or logs | Never asked for; a 13-digit number is refused and not stored |
| Plan prices on WhatsApp drift from the website | The plans test fails the pull request |
| Sensitive documents linger at Twilio | Deleted after forwarding; anything too large is flagged in the email |
| Message history kept forever | The retention job, once open decision 1 is settled |
| Costs creep up with long conversations | One message per answer where possible; the rating step is short |
