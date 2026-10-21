# How Induduzo's WhatsApp works today

A plain explanation of the WhatsApp setup as it stands on **21 Oct 2026**, for
demos and for anyone who needs the whole picture fast. The build plan for what
comes next is `docs/feature-3-whatsapp-line.md`; the setup history is
`docs/twilio-setup.md`.

---

## The one-minute version

- Induduzo has a WhatsApp business line: **073 731 0521**.
- It isn't a phone. It lives in **Twilio**, a messaging service, which is
  connected to **Meta** (WhatsApp's owner) through Induduzo's WhatsApp Business
  account.
- **Going out:** when a family completes the registration on the website, our API
  asks Twilio to send them a WhatsApp confirmation from that line.
- **Coming in:** families can message the line. Today those messages are stored
  in Twilio and nobody is told. Automatic replies are the next thing being built.
- **Where it runs:** on the **internal** environment, with test data. The live
  website doesn't use the API yet.

---

## The pieces

```
  Family's phone
       │  WhatsApp
       ▼
  Meta (WhatsApp)  ◀──────────────▶  Twilio  ◀──── our API (Railway, internal) ◀── website form
  WhatsApp Business account          sender 073 731 0521        │
  "Induduzo"                         message template           ├──▶ database (Railway Postgres)
                                     message logs               └──▶ office email (admin@induduzo.co.za)
```

| Piece | What it does | Where you look |
|---|---|---|
| **Meta: WhatsApp Business account "Induduzo"** | Owns the right to use 073 731 0521 on WhatsApp, and approves message templates | business.facebook.com → WhatsApp Manager |
| **Twilio** | Sends and receives the messages for us; keeps a log of every one; holds the template | console.twilio.com |
| **The sender** | 073 731 0521 registered in Twilio, display name "Induduzo", status **Online** since 20 Oct 2026 | Twilio → Messaging → Senders → WhatsApp senders |
| **The template** | The approved wording for messages Induduzo starts: `induduzo_registration_confirmation` | Twilio → Messaging → Content Template Builder |
| **Our API** | Saves the registration, emails the office, and asks Twilio to send the WhatsApp | Railway → internal → api |
| **The website** | The registration form a family fills in | site-internal.up.railway.app |

---

## Going out: the registration confirmation

What happens when a family registers on the website:

1. **Step 1 of the form** (name, mobile, plan, consent). The API saves a lead
   with a reference like `IND-2026-001234` and emails the office.
2. **Step 2 of the form** (ID number, address, plan, burial place, terms). The API
   saves the application and emails the office again.
3. Straight after step 2, the API asks Twilio to send this WhatsApp from 073 731
   0521 to the mobile number on the form:

   > Sawubona **{first name}**, thank you for registering with Induduzo Funeral Home.
   >
   > Your reference is **{reference}**.
   >
   > A family liaison will call you within one working day. We will never ask for
   > your bank card details by message.
   >
   > Siyazazi Izingxaki Zakho.

   The first name and reference are filled in for each family. The wording itself
   is fixed: it's the template Meta reviews once, then it works for everyone.

4. Twilio tells WhatsApp to deliver it, and logs the result: sent, delivered,
   read, or failed with an error code.

**A failed WhatsApp never loses a registration.** The registration is saved and
the office is emailed first; the WhatsApp is sent afterwards, and if it fails the
API logs it and moves on.

### Why the template needs Meta's approval

WhatsApp only lets a business **start** a conversation with wording Meta has
approved in advance. That stops businesses spamming people. The confirmation is
business-started (the family filled in a website form, they didn't message us),
so it must use the approved template.

- Submitted to Meta on **20 Oct 2026**, as a **Utility** message (a confirmation
  of something the person just did, which is cheaper than Marketing).
- **Status on 21 Oct: under review.** Meta usually decides within 24–48 hours.
- Until it's approved, Twilio accepts the send but WhatsApp doesn't deliver it.
  Twilio's log shows error **63016** ("Outside messaging window. For WhatsApp, use
  a Message Template instead"). That's what happened to test IND-2026-001004 on
  20 Oct: everything on our side worked, and only Meta's approval was missing.

### The 24-hour window

If a family **messages the line first**, WhatsApp opens a 24-hour window. Inside
it, the business can reply with any wording, no template needed. This is what the
automatic replies being built next will use. Outside the window, only approved
templates can be sent.

---

## Coming in: messages to the line

- Anyone can WhatsApp 073 731 0521 now.
- The message arrives at Twilio, not on a phone. **Nobody is notified and nothing
  replies yet.**
- To read them: **Twilio Console → Monitor → Logs → Messaging**. Rows marked
  **Incoming** with "To" = +27 737310521 are messages to the line. Click the date
  to see the text.
- Times in that log are **US Pacific time**, 9 hours behind South Africa.

**Never set 073 731 0521 up in the WhatsApp or WhatsApp Business app on a phone.**
A number can only be in one place, so that would pull it away from Twilio and
break everything above.

---

## What's switched on where

| | Internal (testing) | Production (live) |
|---|---|---|
| Website form → API | Yes: site-internal → api-internal | Not yet: the API isn't deployed for production |
| Database | Railway Postgres, **test data only** | Not yet chosen |
| Office emails | Yes, to admin@induduzo.co.za | — |
| WhatsApp confirmation | Yes: all four Twilio settings are on the internal API (20 Oct). Delivers once Meta approves the template | — |
| Messages to the line | Stored in Twilio only | — |
| Website "WhatsApp us" button | Still 079 751 0648 (answered by staff in the WhatsApp app) | Still 079 751 0648 |

Important while testing on internal: **the confirmation goes to whatever mobile
number is typed on the form.** Only use your own numbers there.

The four Twilio settings on the internal API (names only; the values are in
Railway, and the auth token is sealed):

| Setting | What it is |
|---|---|
| `TWILIO_ACCOUNT_SID` | Which Twilio account |
| `TWILIO_AUTH_TOKEN` | The account's password for the API. Sealed; never shared |
| `TWILIO_WHATSAPP_FROM` | The line: +27737310521 |
| `TWILIO_CONTENT_SID` | Which template to send (starts with `HX`) |

A quick health check: https://api-internal-8e41.up.railway.app/health shows
`"whatsapp":"configured"` when all of these are in place. That proves the
settings are there, not that a message was delivered; Twilio's log proves that.

---

## How to demo it

**The confirmation (once Meta has approved the template):**
1. Open https://site-internal.up.railway.app/register on a laptop.
2. Fill in step 1 with a test name and **your own mobile number**, tick the
   contact consent, Continue. Point out the reference on the next page.
3. Fill in step 2 (a made-up ID number that passes the check, an address, a plan,
   burial place, tick the terms) and submit.
4. Show, within a minute:
   - the WhatsApp arriving on your phone from 073 731 0521 (WhatsApp may show it
     as "Induduzo"), with your name and the reference;
   - the two office emails at admin@induduzo.co.za;
   - the message in Twilio's log, status **Delivered**, then **Read** once opened;
   - the new enquiry in the staff portal (portal-internal.up.railway.app).

**Messages to the line:**
1. From your phone, WhatsApp 073 731 0521.
2. Open Twilio → Monitor → Logs → Messaging and show it arriving as **Incoming**.
3. Explain that today nobody is told and nothing replies, and that the menu below
   is what changes that.

---

## What's being built next: automatic replies

Planned in `docs/feature-3-whatsapp-line.md`. Rules only, no AI:
- Any message gets a greeting and a numbered menu:
  1. someone has passed away;
  2. plans and prices;
  3. join a plan;
  4. paying;
  5. my policy;
  6. branches and hours;
  7. talk to a person.
- Option 1 always answers immediately with the 24-hour numbers.
- Families can register over WhatsApp, and add family members' names,
  relationships and dates of birth. ID numbers stay on the liaison call.
- Anything the menu can't handle becomes a callback for staff, timed to office
  hours (Mon–Fri 08:00–17:00, Sat 08:00–13:00).
- After each answer, "Did this help?", then a 1–5 rating.
- English first, isiZulu next.

---

## What it costs

- **Twilio:** a small fee per message, in and out.
- **Meta:** about $0.0076 per Utility template message in South Africa, and a
  charge on replies inside the 24-hour window since 1 Oct 2026.
- **The line itself:** about $1.15 a month.
- Roughly **R50 a month** for 100 confirmations. A menu conversation of 6–10
  messages is about **R1–R2**.

---

## If something isn't working

| You see | It means | Do this |
|---|---|---|
| Twilio log: **63016** | The template isn't approved yet, and the family hasn't messaged the line in the last 24 hours | Wait for Meta's approval (Twilio → Content Template Builder shows the status) |
| `/health` says `"whatsapp":"not_configured"` | One of the four settings is missing, or the API hasn't redeployed since they were added | Check Railway → internal → api → Variables, then redeploy the api |
| Railway banner "builds paused" | A Railway-wide problem | Wait; then redeploy the api |
| Meta shows the number as **Pending** with "reach out to Twilio" | Twilio's sender wizard didn't finish | Twilio → WhatsApp senders → Create new sender → My own phone number → Continue with Facebook; in Meta's popup press **Continue to feature setup** at the end |
| Twilio asks you to sign in | Its session ended in that browser | Sign in again |

---

## Words you'll hear

| Word | Means |
|---|---|
| **Sender** | A phone number registered with Twilio to send and receive WhatsApp messages |
| **Template** | Wording Meta has approved for messages a business starts |
| **Content SID** | Twilio's id for a template; starts with `HX` |
| **24-hour window** | After a family messages the line, 24 hours in which the business can reply freely |
| **Webhook** | Twilio calling our API to say "a message just arrived" (being built) |
| **MessageSid** | Twilio's id for one message; starts with `SM` or `MM` |
| **Internal** | The testing copy of the system on Railway, with test data |
