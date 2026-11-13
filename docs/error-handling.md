# Errors, request ids and triage

How a problem is reported, found and fixed. Written for whoever picks up a
ticket, person or AI. The code is the authority:
[`backend/app/errors.py`](../backend/app/errors.py) holds every code and its
fix, and [`backend/app/request_context.py`](../backend/app/request_context.py)
holds the request id.

## What every error carries

```json
{ "detail": "Our system is busy right now. ...",
  "code": "database_unavailable",
  "request_id": "4f1c09a2e7b84d6a9a3c5be1f0d2a7e1" }
```

| Field | For | Rule |
|---|---|---|
| `detail` | the screen | A sentence a family or staff member can act on. Never internals. |
| `code` | triage | Stable, from `CATALOG`. Never renamed: old tickets must still resolve. |
| `request_id` | the logs | Same as the `X-Request-ID` header and the `[...]` on every log line written for that request, background emails and WhatsApps included. |

A `422` also carries `field_errors` keyed by field name. `429` and `503`
carry `Retry-After`.

The site's `RegistrationError` and the portal's `ApiError` keep `code` and
`requestId`, so a toast or a "report a problem" button can quote them. A
browser that never reached the API reports `network_unreachable`, with no
request id.

## Failures nobody sees at the time

Email and WhatsApp go out after the response, so a failure there cannot be
shown to the person who filled in the form. It is recorded on the enquiry
instead, and the lead is kept regardless:

| Event | `payload.error` |
|---|---|
| `lead_email_failed`, `application_email_failed`, `applicant_email_failed` | an `email_*` code; `smtp_status` holds the server's number |
| `whatsapp_failed` | a `whatsapp_*` code, or `twilio_<n>` (Twilio's own error number) |

These are what a future "this email didn't go through" notice reads: the code
says why, `describe(code)` says what to do. They never hold the server's own
text, because a refusal quotes the recipient's address.

## Triage, in order

1. **Read the code** in `CATALOG`: meaning, usual cause, fix, and `who`
   (`family`, `staff`, `owner` for settings, `developer` for code).
2. **Find the request** in the Railway log by its `request_id`. Every line
   for that request carries it; a `500` has its traceback there.
3. **Check `/health`** for anything `not_configured` or `down`.
4. **Fix where `who` points.** A setting: change it on Railway and redeploy.
   Code: fix it, then add a test that reproduces the ticket.
5. **Never** paste a family's name, number or ID into a ticket, commit or
   log. The reference (`IND-2026-001234`) and the request id are enough.

## The checks that hold this in place

Run against a throwaway Postgres as `induduzo_api` (see ARCHITECTURE.md §9):

| File | What it proves |
|---|---|
| `tests/test_business_flows.py` | 200 registrations through a real Uvicorn server, 8 at once, real SMTP: every message accounted for, stored exactly as typed, one email each, no personal data in any log. `FLOW_REPORT=report.json` keeps the per-message report |
| `tests/test_email_delivery.py` | Mail through smtplib to `tests/smtp_sink.py`, and each way it fails (no login, wrong password, refused, timeout, no TLS...) recorded as its code |
| `tests/test_hostile_input.py` | What the public form refuses (NUL, formulas, invisible characters, multi-address email, oversized bodies) and what it must still accept (real names, emoji in notes) |
| `tests/test_dependency_overrides.py` | Every staff route lets in exactly the roles it declares; a database, sender or sign-in outage on each major call is a coded answer |
| `tests/test_database_security.py` | What the API's login may do, that it reaches every table, and that Supabase's public roles reach nothing |
| `tests/test_staff_search.py` | Staff search sent in the body answers exactly as the old URL form did |
| `tests/test_error_contract.py` | The body, the headers and the log redaction above; every raised code is catalogued |
