# Induduzo Email Setup Plan

Creating 5 mailboxes on **induduzo.co.za**:
`ops@`, `fsp@`, `info@`, `admin@`, `management@induduzo.co.za`

---

## How the pieces fit (read this first)

Three separate things are involved — don't confuse them:

1. **Domain registrar** = domains.co.za (where induduzo.co.za is registered). ✅ You have this.
2. **Website host** = Netlify (serves your site). ✅ You have this. **Netlify does NOT provide mailboxes.**
3. **Email host** = a separate mailbox service you need to add. ❌ This is the missing piece.

**Critical detail about your DNS:** induduzo.co.za's nameservers are
`dns1.p07.nsone.net` and `dns2.p07.nsone.net` — **that is Netlify's DNS.**
So even though the domain is registered at domains.co.za, its live DNS is controlled inside **Netlify**.

➡️ **All mail records (MX, SPF, DKIM) must be added in the Netlify dashboard, not at domains.co.za.**
The "Edit DNS Records" button at domains.co.za will have no effect while the nameservers point to Netlify.

---

## Recommended: domains.co.za "Email Only 10" — R69/month

Best fit because it lives in the account you already have (one login, one bill), gives 10 mailboxes
(you need 5), and supports proper IMAP/POP so it works in Outlook and phone mail apps.

### Step 1 — Clear account verification (if it blocks you)
Your domains.co.za dashboard shows **"Awaiting Document Upload."** You may need to upload an ID/
proof document before you can buy a service. Dashboard → click the "Click here" verification notice →
upload the requested document. (If purchase works without it, skip this.)

### Step 2 — Buy the email plan
1. Log in at domains.co.za → **Manage Services → Email Only Hosting**.
2. Choose **Email Only 10 (R69/mo)** → **Buy Now**.
3. When asked which domain, select **induduzo.co.za**.
4. Complete checkout / payment.

### Step 3 — Create the 5 mailboxes
1. After purchase, open the email service's **control panel** (from Manage Services → your new email
   product → Login / Manage).
2. Create each mailbox and set a strong password for each:
   - `ops@induduzo.co.za`
   - `fsp@induduzo.co.za`
   - `info@induduzo.co.za`
   - `admin@induduzo.co.za`
   - `management@induduzo.co.za`

### Step 4 — Copy the exact DNS records domains.co.za gives you
In the email control panel (or the welcome email you receive), find the **email DNS settings** for the
domain. Copy these exactly — the values are specific to your account:
- **MX record(s)** — the mail server hostname(s) and priority (e.g. priority 10).
- **SPF record** — a TXT record, usually like `v=spf1 include:... ~all`.
- **DKIM record** — a TXT (or CNAME) record for mail authentication.
- (Optional) any **autodiscover CNAME**.

> Can't find them? Call domains.co.za support on **011 640 9700** and ask for "the MX, SPF and DKIM
> records for my Email Only hosting on induduzo.co.za." Don't guess these — wrong MX = no email.

### Step 5 — Add those records in Netlify (this is where DNS lives)
1. Log in to **Netlify** → **Domains** (top nav) → click **induduzo.co.za**.
2. You'll see the DNS records panel. For each record from Step 4, click **Add new record**:
   - **MX:** Type = `MX`, Name = leave blank / `@` (the root domain), Value = the mail hostname from
     Step 4, Priority = as given (usually 10). Add one row per MX value.
   - **SPF:** Type = `TXT`, Name = `@`, Value = the SPF string. (If an SPF TXT already exists, merge —
     don't create a second one.)
   - **DKIM:** Type = `TXT` (or `CNAME` if that's what they gave), Name = the selector they specify
     (e.g. `default._domainkey`), Value = the DKIM string.
3. Save.

### Step 6 — Wait, then test
- Allow **2–3 hours** for propagation (can be up to 24–48h).
- Send a test email **to** `info@induduzo.co.za` from a Gmail/other account, and reply **from** it.
- Both directions working = done.

### Step 7 — Log in / connect devices
- **Webmail:** use the webmail URL domains.co.za provides (often `mail.induduzo.co.za` or a link in
  the panel).
- **Outlook / phone:** add an **IMAP** account using the incoming/outgoing server, ports and SSL
  settings shown in the email control panel (typically IMAP 993 SSL, SMTP 465 SSL).

---

## Zero-cost alternative: Zoho Mail (Free)

If you'd rather not pay monthly: Zoho Mail's **Forever Free** plan gives exactly **5 users** free, 5GB
each, on one domain. Trade-off: **webmail + Zoho mobile app only — no IMAP/Outlook** on the free tier.
Setup is the same shape: create the 5 users in Zoho, then add **Zoho's** MX + SPF + DKIM records in
**Netlify** (Step 5 above), using the values Zoho shows during its domain-verification wizard.

---

## Quick checklist

- [ ] Account verification cleared (if required)
- [ ] Email plan purchased for induduzo.co.za
- [ ] 5 mailboxes created (ops, fsp, info, admin, management)
- [ ] MX / SPF / DKIM values copied from the email host
- [ ] Those records added in **Netlify** DNS (not domains.co.za)
- [ ] Waited for propagation
- [ ] Test email sent + received
- [ ] Webmail / Outlook / phone connected

---

### One-line summary
Buy **domains.co.za "Email Only 10" (R69/mo)** for induduzo.co.za, create the 5 mailboxes, then add the
**MX/SPF/DKIM records inside Netlify** (because your DNS is delegated to Netlify) — wait a couple of
hours and test.
