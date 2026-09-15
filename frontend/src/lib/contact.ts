/**
 * Contact details, in one place.
 *
 * Induduzo publishes two mobile numbers. The first is the primary: it is what
 * single-number surfaces (the header call button, WhatsApp) use. Surfaces with
 * room to list both — the Contact page and the footer — map over CONTACT_PHONES.
 */

export interface ContactPhone {
  /** How it is shown to a person reading the page. */
  display: string;
  /** E.164, for tel: links and anything machine-readable. */
  e164: string;
  /** tel: href. */
  link: string;
  /** wa.me link for this number. */
  whatsapp: string;
}

const phone = (display: string, e164: string): ContactPhone => ({
  display,
  e164,
  link: `tel:${e164}`,
  whatsapp: `https://wa.me/${e164.replace("+", "")}`,
});

export const CONTACT_PHONES: ContactPhone[] = [
  phone("079 751 0648", "+27797510648"),
  phone("082 954 9241", "+27829549241"),
];

export const [PRIMARY_PHONE] = CONTACT_PHONES;

// Single-number aliases, kept so every existing call site keeps working.
export const CONTACT_PHONE_DISPLAY = PRIMARY_PHONE.display;
export const CONTACT_PHONE_E164 = PRIMARY_PHONE.e164;
export const CONTACT_PHONE_LINK = PRIMARY_PHONE.link;
export const WHATSAPP_URL = PRIMARY_PHONE.whatsapp;

export const CONTACT_EMAIL = "Info@induduzo.co.za";
export const CONTACT_EMAIL_LINK = `mailto:${CONTACT_EMAIL}`;

export const CONTACT_ADDRESS = "Edendale Main Road, Kwadaya, Pietermaritzburg, KwaZulu-Natal 3201";
export const CONTACT_MAPS_URL =
  "https://www.google.com/maps/place/Induduzo+Funeral+Home/@-29.6482444,30.3186257,17z/data=!3m1!4b1!4m6!3m5!1s0x1ef6a2e73a0f7019:0x2cad98db42535559!8m2!3d-29.6482444!4d30.3186257!16s%2Fg%2F11jwswk2nl";
export const CONTACT_REVIEW_URL =
  "https://search.google.com/local/writereview?placeid=ChIJGXAPOuei9h4RWVVTQtuYrSw";
