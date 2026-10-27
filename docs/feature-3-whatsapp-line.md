# Feature 3 — One WhatsApp line that sends, receives and answers

**Working brief for whoever works on this, including an agent picking it up cold.**
Read `ARCHITECTURE.md` and `docs/twilio-setup.md` first.

| | |
|---|---|
| Status | **Built** (27 Oct 2026): the inbound webhook, the menu, escalations to staff, the office email, the portal's WhatsApp screen under Growth, delivery reports and the safety-net job. **Not live yet**: Twilio's webhooks still have to point at the API (§9, W6) |
| Code | `backend/app/services/whatsapp_content.py` (the words), `whatsapp_menu.py` (the engine), `whatsapp_line.py` (records), `routers/whatsapp.py`, migration `0018`, `portal/src/pages/WhatsApp.tsx` |
| Tests | `backend/tests/test_whatsapp_menu.py` (every menu path, office hours, plans match the website), `test_whatsapp_line.py` (webhooks end to end) |

---

## 1. What this is

Induduzo's WhatsApp line is **073 731 0521** (+27 73 731 0521), a Twilio
WhatsApp sender with the display name "Induduzo". It replaced 069 706 0387 on
20 Oct 2026 (migration 0017). The owner's goal, for transparency and trust, is
that **the number that sends a family their confirmation is the same number
they can message back**, that every message gets an immediate, useful answer,
day or night, and that **a person is only involved when a family asks for one**.

So the line:

1. **Sends** the registration confirmation, as before.
2. **Receives** every message and stores it, linked to the family's enquiry or
   member record when the number matches.
3. **Answers** with an automatic menu (§5): seven of the questions a funeral
   home is asked most, each with its own answers. Rules only, no AI.
4. **Hands over** only when the family asks for a person: "None of these" or
   "No, I need more help", then **WhatsApp me** or **Phone me**. Only then is
   the office emailed and the conversation shown in the portal.
5. Lets **staff reply from the portal**, from the same number, while the
   conversation is escalated and WhatsApp's 24-hour window is open.

The website's "WhatsApp us" button stays on 079 751 0648 until this is live on
the real number (W8).

---

## 2. Decisions taken

| Decision | Choice | Who, when |
|---|---|---|
| The line | **073 731 0521**. 069 706 0387 is retired | Owner, 20 Oct 2026 |
| Automatic replies | A rule-based menu. **No AI** for Induduzo | Owner, 21 Oct 2026 |
| The menu | **Seven topics drawn from the questions and complaints a funeral home gets most**, so a family isn't forced to wait for a person. Each topic has sub-options with answers, and ends with "None of these" | Owner, 27 Oct 2026 |
| When staff are involved | **Only when a family asks for a person** and picks WhatsApp or a call. Menu answers are never emailed or listed | Owner, 27 Oct 2026 |
| The office email | One per escalation to admin@induduzo.co.za: *"Please respond to <name> using the system, or call them"*, with a link to the conversation. Bereavements are marked urgent | Owner, 27 Oct 2026 |
| Staff replies | From the portal's WhatsApp screen under Growth, **only on an escalated conversation** | Owner, 27 Oct 2026 |
| Office hours | **Mon–Fri 08:00–17:00, Sat 08:00–13:00** (South African time). Sundays and public holidays are closed. Asking for a person out of hours still works; the family is told when the office opens | Owner, 21 Oct 2026 |
| Family details over WhatsApp | **Never ID numbers.** Any run of 13 or more digits is removed before storing, and Twilio's copy is deleted | Owner, 21 Oct 2026 |
| Joining over WhatsApp | **Not in the menu.** "How to join" links to the website's registration, which already captures consent and sends the confirmation. The planned WhatsApp registration (old M3, M4) is dropped | 27 Oct 2026, following the owner's new menu design |
| Language | English first, isiZulu next (M5) | Owner, 21 Oct 2026 |
| Website button | Stays on 079 751 0648 until this works on the real number | Owner, 19 Oct 2026 |

## 3. Still open

| # | Question | Recommendation | Needed by |
|---|---|---|---|
| 1 | **The owner checks every answer's wording** in `whatsapp_content.py`. Nothing promises a payout date or a response time; claims and waiting-period answers say what the website says and send anything specific to a person | A read-through with the owner, then a text-only pull request | Before W8 |
| 2 | How long messages are kept (POPIA: no longer than needed) | 24 months, then deleted by a job; Twilio's copies of photos deleted at the same time | Before production |
| 3 | The isiZulu wording of every menu message | Written once the English is settled, then checked by a first-language speaker on staff | M5 |
| 4 | Public holidays after 2027 | Add each year's list to `PUBLIC_HOLIDAYS` | Dec 2027 |

---

## 4. How it works

```
 Family's WhatsApp ──▶ Twilio (073 731 0521) ──▶ POST /api/whatsapp/inbound
                                                   1. check X-Twilio-Signature (403 if wrong)
                                                   2. store the message, once per MessageSid,
                                                      with any 13+ digit number removed
                                                   3. match the number to an enquiry or member
                                                   4. run the menu under a row lock: read the
                                                      conversation's step, choose the reply,
                                                      save the new step
                                                   5. answer 200 with empty TwiML, at once
                                                        │ after the commit, in the background
                                                        ▼
                                                   6. send the menu's reply through the API,
                                                      and store it
                                                   7. if they asked for a person: email admin@
                                                   8. if a number was removed: delete Twilio's copy

 Every message sent ──▶ Twilio status callback ──▶ POST /api/whatsapp/status
                                                   queued → sent → delivered → read (or failed)
```

- **Store first, then reply.** A Twilio or mail failure must never lose a
  message. Twilio doesn't retry a webhook that fails, so the endpoint stores and
  answers quickly; the safety-net job (§9) catches what it misses.
- **Replies go through the API, not TwiML,** so each is stored with its own
  MessageSid and reports delivered and read.
- **Menu replies need no template.** A family who writes opens WhatsApp's
  24-hour window; replies inside it are ordinary messages. Only messages
  Induduzo starts, like the confirmation, need an approved template.

---

## 5. The menu

The words live in `backend/app/services/whatsapp_content.py` and nowhere else.
Changing an answer is a text edit and a pull request. `tests/test_whatsapp_menu.py`
checks that every option leads somewhere, every message fits in one WhatsApp,
the menu never asks for an ID or card number, and the plan names and prices
match `frontend/src/data/plans.ts`.

### 5.1 The topics

Any first message, or any message after 30 minutes' silence, gets the greeting
and the seven topics:

| # | Topic | Its options |
|---|---|---|
| 1 | **Someone has passed away** | The 24-hour numbers come first, in the same message. Please phone me now (an **urgent** escalation, day or night) · What happens next? · Documents for the claim · None of these |
| 2 | Claims and payouts | Documents I need · How the payout works · My claim is taking long · Claiming in the waiting period · None of these |
| 3 | Paying my premium | Ways to pay (never account numbers) · I missed a payment · Wrong amount or double deduction · Changing or cancelling my debit order · None of these |
| 4 | My policy and family members | Adding or removing family members · Changing my beneficiary or contact details · What my plan covers (the plans topic) · A copy of my policy · None of these |
| 5 | Plans, prices and joining | Plan A · Plan B · Plan C · Dome Plan · How to join (the website) · None of these |
| 6 | Funeral arrangements | Collecting my loved one · Booking the funeral date · Tent, chairs, hearse and programmes · A funeral at the family home · None of these |
| 7 | Complaints, compliments and contact | Make a complaint (straight to "how should we contact you?") · Pay a compliment (a rating) · Our office and hours · Phone numbers and email · None of these |

### 5.2 After an answer

*"Did this answer your question? 1 Yes · 2 No, I need more help · 0 Main menu"*

- **Yes** asks for a rating from 1 to 5, then an optional comment. A rating of 1
  or 2 offers a person.
- **No** goes to §5.3, about that answer.

### 5.3 Asking for a person

"None of these", "No, I need more help", a complaint, or two replies in a row
the menu didn't understand, all lead here:

> Sorry we couldn't answer that here. You can:
> 1. Go back
> 2. A person replies to me here on WhatsApp
> 3. A person phones me
> 0. Main menu
>
> Our office is open Mon–Fri 8am–5pm and Sat 8am–1pm.

Picking 2 or 3 opens an **escalation**:

- It is stored with the topic, the channel, and whether it was out of hours.
- The office is **emailed once** (§8). Asking again, for example after going
  back to the menu, updates the same escalation rather than emailing twice.
  Becoming a bereavement emails again, marked urgent.
- The family is told what happens next: *"as soon as possible"* in office
  hours, or *"when it opens at 08:00 on Monday"* outside them, always with the
  24-hour numbers out of hours.
- While it is open the menu stays quiet. If the family writes again and nobody
  has replied in the last hour, they hear *"we have your message"*, at most once
  an hour. **MENU** takes them back to the menu without closing it.

### 5.4 Everywhere

- **0** or **menu** goes to the main menu; **hi**, **sawubona** and similar
  greet them again.
- Numbers are read the way people type them: "2", "2.", "(2)", the 2️⃣ emoji.
- **STOP** switches off automated messages for that number. Messages are still
  stored, and **START** switches them back on.
- A photo in the menu gets *"We can't open photos or documents in this menu"*.
  In an escalated conversation staff can open it in the portal.
- An ID or card number is removed before storing, the family is told not to
  send one, and Twilio's copy is deleted.

---

## 6. Data model

Migration `0018_whatsapp_conversations.sql`. The usual house style: `tenant_id`
on every row; RLS on; a policy for `induduzo_api` only; nothing for `anon` or
`authenticated` (SECURITY.md rule 8); no DELETE.

| Table | What |
|---|---|
| `whatsapp_conversations` | One row per family number: its menu step (`state`), where "back" leads (`data`), misses in a row, STOP, last message times, and the matched enquiry or member |
| `whatsapp_messages` | Every message both ways, keyed by `twilio_sid`. `author` is `family`, `menu`, `system` (the confirmation) or the staff member's email. `status` follows Twilio's reports and only moves forward. Media is stored as Twilio media SIDs, never URLs |
| `whatsapp_escalations` | `channel` (whatsapp, call), `topic`, `urgent`, `out_of_hours`, `promised_for`, `notified_at` (the office email), `first_reply_at`, `resolved_at`, `resolved_by`, `resolution_note`. One open per conversation |
| `whatsapp_feedback` | `rating` 1–5 and `comment`, with the topic, and the escalation when staff helped |

`plan_enquiries.whatsapp_message_sid` stays; the confirmation is also written to
`whatsapp_messages`, so a reply to it shows in the conversation.

---

## 7. Settings

| Variable | What |
|---|---|
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`, `TWILIO_CONTENT_SID` | As before. **The auth token also checks every webhook's signature**; without it the webhooks answer 503. Sealed, pasted by the owner |
| `PUBLIC_API_URL` | The API's public address, e.g. `https://api-internal-8e41.up.railway.app`. Behind Railway's proxy the request URL isn't the one Twilio signed, so **webhooks are refused without it**. Also where Twilio sends delivery reports. `/health` shows `whatsapp_webhooks` |
| `PORTAL_URL` | The portal's address, e.g. `https://portal-internal.up.railway.app`. Optional: the office email links straight to the conversation when it is set |
| `WHATSAPP_OUTBOUND` | `off` / `allowlist` / `on`. Applies to **every** message: confirmations, menu replies and staff replies. Internal uses `allowlist`; production `on` |
| `WHATSAPP_TEST_RECIPIENTS` | Comma-separated E.164 numbers, internal only |

Office hours and public holidays are in the content file, not in settings.

---

## 8. Rules

- **Every webhook is signature-checked.** No valid `X-Twilio-Signature`, 403.
  No auth token configured, 503.
- **No message text or numbers in logs.** MessageSids, row ids and menu steps
  only (ARCHITECTURE.md rule 9). A test walks a whole conversation and checks
  the captured logs.
- **Only escalations reach staff.** The email and the portal's list show a
  conversation only once the family has asked for a person. The portal shows
  the menu steps before that, for context, folded.
- **The office email:** subject *"Please respond: WhatsApp from <name>"*, or
  *"URGENT – someone has passed away"*, marked high priority. It carries the
  name and number, so it is never logged; the log line carries `WA-<id>`.
- **Staff replies:** admin and owner only; only on an open escalation; only
  within 24 hours of the family's last message. Outside that, WhatsApp allows
  only approved templates, so the portal says to phone instead.
- **Resolving** closes the escalation and, if the window is open and staff tick
  the box, asks the family to rate the help. The menu then takes over again.
- **Photos and documents** are fetched from Twilio by the API for the portal,
  only in escalated conversations. Twilio keeps its copy until the retention
  job (open decision 2).
- **Cost:** every message is billed, both ways. The menu keeps each answer to
  one message, and the holding reply goes out at most once an hour.

---

## 9. Testing, and going live

**Automated, on every pull request:** `tests/test_whatsapp_menu.py` and
`tests/test_whatsapp_line.py`. Twilio and the mail server are fakes; requests
are signed with a made-up token the way Twilio signs them.

**On internal (W6), with the real line.** Nothing reaches a family: internal is
on `allowlist`.

1. Railway → internal → api: set `PUBLIC_API_URL=https://api-internal-8e41.up.railway.app`
   and `PORTAL_URL=https://portal-internal.up.railway.app`. Deploy.
   `/health` should say `"whatsapp_webhooks": "configured"`.
2. Twilio → Messaging → Senders → WhatsApp senders → 073 731 0521:
   - "Webhook URL for incoming messages": `https://api-internal-8e41.up.railway.app/api/whatsapp/inbound` (POST)
   - "Status callback URL": `https://api-internal-8e41.up.railway.app/api/whatsapp/status`
3. From the owner's phone (on `WHATSAPP_TEST_RECIPIENTS`), write "hi" and walk
   every topic. Each answer should arrive within seconds.
4. Ask for a person. The email should reach admin@ with a link, and the
   conversation should appear under Growth → WhatsApp, with a badge on Growth.
5. Reply from the portal; it should arrive on the phone. Resolve it; the phone
   should be asked for a rating.
6. Send an ID-shaped test number (not a real ID); the portal should show it
   removed.
7. A message from a phone not on the allowlist is stored and gets no reply.

**The safety net** runs as a command until a scheduler exists (CLAUDE.md):

```bash
python -m app.jobs.whatsapp_backfill
```

It emails the office about any escalation whose email didn't go, and stores
any messages from the last 6 hours that the webhook missed. Hourly is the
intention.

---

## 10. Build tracker

| Bit | What | Status |
|---|---|---|
| W1 | Outbound switch with the internal allowlist; `PUBLIC_API_URL`; stop two log leaks | Done (#20) |
| W2 | `whatsapp_messages`; store outbound messages and the confirmation; signed status callbacks | Done (this PR) |
| W3 | Inbound webhook: signature, store once, match, STOP/START, ID numbers removed | Done (this PR) |
| M1 | Menu engine and content: seven topics, answers, 0/menu, misunderstood replies, 30-minute restart, the plans test | Done (this PR) |
| M2 | Asking for a person, office hours and holidays, "Did this help?", ratings and comments | Done (this PR) |
| W4 | The office email, for escalations only; photos viewable in the portal | Done (this PR). Changed from "forward everything" by the 27 Oct decision |
| W5 | Safety net: re-send failed escalation emails, store missed messages | Done (this PR) |
| W9 | Portal: WhatsApp screen under Growth, the badge, the statistics | Done (this PR) |
| W10 | Replies from the portal (24-hour window) | Done (this PR) |
| W6 | Point Twilio's webhooks at internal and walk every path (§9) | **Next.** Needs this on internal, and Railway building again |
| — | Owner reads every answer (open decision 1) | Before W8 |
| W8 | Move the website's WhatsApp button to 073 731 0521 | After W6 and the production API |
| M5 | isiZulu: language choice on the greeting, the whole menu in isiZulu | After the English is settled |
| — | Retention job, Twilio media deletion (open decision 2) | Before production |
| M3, M4 | Joining and family details over WhatsApp | Dropped (27 Oct): "How to join" links to the website |

---

## 11. Risks

| Risk | Handled by |
|---|---|
| API down when a message arrives | Twilio doesn't retry; the backfill stores it, and the menu answers the family's next message |
| A bereaved family meets a menu | Topic 1 gives the 24-hour numbers in the same message, and "Please phone me now" escalates as urgent at any hour |
| Email fails | The escalation is stored and shown in the portal; the backfill re-sends the email |
| Forged webhook calls | Signature check against the auth token; 403 otherwise |
| A test messages a real family | `WHATSAPP_OUTBOUND=allowlist` on internal, for every message |
| ID or card numbers in chats or logs | Never asked for; removed before storing; Twilio's copy deleted |
| Plan prices on WhatsApp drift from the website | The plans test fails the pull request |
| A family waits with nobody replying | The badge on Growth, the email, and a holding reply at most once an hour |
| Costs creep up | One message per answer; holding replies at most hourly |
