# Twilio WhatsApp — going live

**Status at time of writing (14 September 2026): the registration confirmation
has never sent a real message.** `TWILIO_CONTENT_SID` is blank, so
`send_registration_confirmation()` silently takes its sandbox fallback path and
writes a log line instead of sending.

No application code needs to change to fix this. `backend/app/services/whatsapp.py`
already has the approved-template path; it is skipped only because the content
SID is empty. What follows is console work and environment wiring.

---

## 1. Before anything else — start the approval

Meta template approval is the long pole. Start it on day one; everything else
here takes under an hour.

1. A **Twilio account** with a payment method.
2. A **Meta Business Manager** account, linked to Twilio, with **business
   verification** completed. Verification requires documents proving the
   business exists and can take a few days.
3. Twilio Console → **Messaging → Senders → WhatsApp senders** → register the
   business number.

The number must be one that is **not already registered to a personal WhatsApp
or WhatsApp Business app account.** If it is, deregister it there first, or the
sender registration will fail with an error that does not explain itself.

---

## 2. The template

Register it as a **Utility** template, not Marketing.

It confirms a transaction the person has just initiated, which is exactly what
Utility is for. It is also roughly five times cheaper: in South Africa Meta
charges about **$0.0076** per utility message against **$0.0379** for marketing.
Submitting a transactional confirmation as Marketing would be both wrong and
expensive.

### The body must have exactly two placeholders

`whatsapp.py` sends this and nothing else:

```python
params["content_variables"] = json.dumps({"1": first_name, "2": reference})
```

So the template takes `{{1}}` = first name and `{{2}}` = reference, in that
order. A template with three placeholders, or with them in the other order, will
either be rejected by Twilio at send time or deliver visibly wrong text.

Keep the wording aligned with the sandbox fallback in `_plain_body()`
(`whatsapp.py:32`) so the two paths read the same:

> Sawubona {{1}}, thank you for registering with Induduzo Funeral Home.
>
> Your reference is {{2}}.
>
> A family liaison will call you within one working day. We will never ask for
> your bank card details by message.
>
> Siyazazi Izingxaki Zakho.

That last line about bank card details is deliberate and worth keeping: it is a
standing anti-fraud message, and this is the one channel where a family will
believe a message is really from Induduzo.

When it is approved, copy the **Content SID** — it starts `HX`.

---

## 3. Environment

Set these in `backend/.env`, which is gitignored. **Never** put a real value in
`backend/.env.example`; that file is committed to a public repository.

```
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_FROM=+27...
TWILIO_CONTENT_SID=HX...
```

`TWILIO_WHATSAPP_FROM` is a **bare E.164 number**. Do not prefix it with
`whatsapp:` — `whatsapp.py:67-68` adds that itself, and doing it twice produces
`whatsapp:whatsapp:+27...` and a confusing Twilio error.

---

## 4. Three traps

**`/health` will lie to you.** `whatsapp_enabled` (`config.py:119-125`) is
`account_sid and auth_token and whatsapp_from` — it deliberately **excludes**
`content_sid`, so health reports WhatsApp as configured while sends are still
falling back to the sandbox path. A green health check is not proof the template
path is live. The proof is a `content_sid` in the outbound request.

**Config resolves once, at import.** `config.py` is a stdlib frozen dataclass,
not pydantic-settings, and its fields are bare `os.getenv(...)` defaults
evaluated when the module is first imported. `main.py` calls `load_dotenv()`
*before* importing config (flagged `# noqa: E402`) for exactly this reason. Any
new entrypoint that imports `app.config` first will read `None` for every
credential and quietly send nothing.

**Failures are swallowed by design.** `send_registration_confirmation()` never
raises. A misconfiguration does not crash anything and does not fail the
enquiry — it just silently stops sending. So verify positively, below, rather
than assuming that no error means success.

---

## 5. Verify

Run the backend, submit a stage-2 application, and check all three of these.

1. **The message arrives** on the test handset.
2. **The database recorded it** — not the failure branch:

```sql
select reference, whatsapp_sent_at, whatsapp_message_sid
  from plan_enquiries where reference = 'IND-...';

select event_type, payload from enquiry_events
 where enquiry_id = '...' order by created_at desc;
```

`whatsapp_sent_at` and `whatsapp_message_sid` must be populated, and the event
must be `whatsapp_sent`, **not** `whatsapp_failed`.

3. **The logs are clean.** Grep the run's output for the test mobile number. It
must not appear — ARCHITECTURE.md rule 9. Log lines carry the reference only.

---

## 6. What this costs

At roughly 100 confirmations a month, Utility category, South Africa:

| | |
|---|---|
| Meta, utility | $0.0076 + 15% VAT = $0.00874 / message |
| Twilio markup | $0.005 / message |
| Per message | ≈ **$0.0137** |
| 100 messages | ≈ $1.37 |
| WhatsApp sender number | ≈ $1.15 / month |
| **Monthly** | ≈ **$2.52 ≈ R50** at R18/USD |

It scales per message, so the Feature 1 review requests would roughly double it.

From **1 October 2026** Meta begins charging for utility and service messages
sent inside the 24-hour service window, which were previously free. That does
not change the figure above — these confirmations are business-initiated and
outside the window, so they were always chargeable.

---

## 7. What is deliberately not done here

The **second** template, for Feature 1's review request, is not set up. It needs
its own approval and its own content SID — `TWILIO_CONTENT_SID` is the
registration confirmation and cannot be reused. See
`docs/feature-1-review-loop.md` §6.3, and note that its "migration 0008" must
now be **0013**.
