/**
 * The office location, in one place.
 *
 * Two surfaces use it: a link that hands the address to whichever map app the
 * device has, and an embedded map underneath that link.
 *
 * The embed needs no Google API key by default — `output=embed` is the classic
 * keyless Maps iframe. Set `VITE_GOOGLE_MAPS_API_KEY` to switch to the Maps
 * Embed API instead, which gives a cleaner card and a stable quota. That key is
 * public by design (it compiles into the bundle), so restrict it to the
 * Maps Embed API and to the site's HTTP referrers in the Google Cloud console.
 */

export const OFFICE_ADDRESS = "Edendale Main Road Kwadaya, Pietermaritzburg 3201";

/** Shown to a reader, one line per array entry. */
export const OFFICE_ADDRESS_LINES = ["Edendale Main Road Kwadaya,", "Pietermaritzburg 3201"];

/**
 * Exact premises coordinates, "lat,lng". Blank falls back to searching for the
 * address, which drops a pin on every match along Edendale Main Road rather
 * than on the office itself. To pin it exactly: open Google Maps, right-click
 * the building, copy the pair it shows, and paste it here.
 */
export const OFFICE_COORDS = "";

/** What both the link and the embed are pointed at. */
const query = encodeURIComponent(OFFICE_COORDS || OFFICE_ADDRESS);

/** Close enough to read street names, wide enough to place the suburb. */
const zoom = OFFICE_COORDS ? 17 : 14;

/**
 * Google's cross-platform maps URL. On Android it opens the Google Maps app (or
 * the app chooser); on iOS it offers Google Maps if installed and Apple Maps
 * otherwise; on desktop it opens maps.google.com. No API key, no SDK.
 */
export const OFFICE_MAP_LINK = `https://www.google.com/maps/search/?api=1&query=${query}`;

const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;

export const OFFICE_MAP_EMBED_SRC = apiKey
  ? `https://www.google.com/maps/embed/v1/place?key=${apiKey}&q=${query}&zoom=${zoom}`
  : `https://www.google.com/maps?q=${query}&z=${zoom}&output=embed`;
