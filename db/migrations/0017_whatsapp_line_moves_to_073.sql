-- 0017 - The WhatsApp line moves to 073 731 0521.
--
-- 0015 recorded 069 706 0387 as the line for automated WhatsApp messages. On
-- 20 Oct 2026 the owner registered 073 731 0521 (+27737310521) with Twilio
-- instead, through Meta's WhatsApp Business account for Induduzo. It came
-- online the same day as a Twilio WhatsApp sender with the display name
-- "Induduzo".
--
-- 069 706 0387 is retired. Its row is archived rather than deleted, so the
-- record of which line was used, and when, stays.
--
-- Safe to run twice. Archiving touches only a row that is still live, and the
-- new row is skipped if a live row for that number already exists.

update business_phone_numbers
   set archived_at = now(),
       notes = coalesce(notes || ' ', '')
               || 'Retired 20 Oct 2026: the WhatsApp line moved to 073 731 0521.'
 where number_e164 = '+27697060387'
   and archived_at is null;

insert into business_phone_numbers
  (number_e164, label, purpose, whatsapp_status, twilio_sender_sid, notes)
values ('+27737310521', 'WhatsApp line', 'whatsapp_api', 'online',
        'XE8cd13d6e5657138d62ec89b703ee6aa8',
        'Registered as a Twilio WhatsApp sender on 20 Oct 2026, display name '
        '"Induduzo". Replaces 069 706 0387. Messages people send to it arrive '
        'at Twilio, not on a phone, and nothing reads them yet.')
on conflict do nothing;
