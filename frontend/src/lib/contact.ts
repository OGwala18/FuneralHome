/**
 * Contact details, in one place.
 *
 * Induduzo publishes two phone numbers. The first, the 24-hour line, is the
 * primary: it is what single-number surfaces (the header call button, the
 * hero's "Call us") use. Surfaces with room to list both — the Contact page and
 * the footer — map over CONTACT_PHONES.
 *
 * 079 751 0648 was the primary until the owner retired it from every public
 * surface (26 Nov 2026). Do not bring it back.
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
  phone("069 706 0387", "+27697060387"),
  phone("082 954 9241", "+27829549241"),
];

export const [PRIMARY_PHONE] = CONTACT_PHONES;

// Single-number aliases, kept so every existing call site keeps working.
export const CONTACT_PHONE_DISPLAY = PRIMARY_PHONE.display;
export const CONTACT_PHONE_E164 = PRIMARY_PHONE.e164;
export const CONTACT_PHONE_LINK = PRIMARY_PHONE.link;

/** The business WhatsApp line (the menu, payments, proof of payment). */
export const WHATSAPP_LINE = { display: "073 731 0521", e164: "+27737310521" };
export const WHATSAPP_URL = "https://wa.me/27737310521";

/** The 24-hour line, for a death at any hour. It is the primary number. */
export const TWENTY_FOUR_HOUR_LINE = PRIMARY_PHONE;

export const CONTACT_EMAIL = "info@induduzo.co.za";
export const CONTACT_EMAIL_LINK = `mailto:${CONTACT_EMAIL}`;

/**
 * Social profiles.
 *
 * A blank URL means "we have the icon but not the page yet" — call sites render
 * the icon without a link rather than sending a visitor nowhere.
 */
export const INSTAGRAM_URL = "https://www.instagram.com/induduzofuneralhome/";
export const FACEBOOK_URL = "";
