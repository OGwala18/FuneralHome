import { init, track, type CustomProperties } from "@plausible-analytics/tracker";

/**
 * Visitor counts and the clicks that matter, through Plausible.
 *
 * Plausible sets no cookies and stores no personal data, so no consent banner
 * is needed. What it is sent is still kept to the minimum: a page path with the
 * query string and fragment removed, an event name, and where on the page the
 * click happened. Never a name, number or anything typed into a form.
 *
 * Bundled from npm rather than loaded from plausible.io, so the CSP only has
 * to allow plausible.io in connect-src, not in script-src.
 *
 * Inert anywhere but the live site, so local development, Netlify deploy
 * previews and the internal environment do not count as visitors.
 */

const SITE_DOMAIN = "induduzo.co.za";
const LIVE_HOSTS = [SITE_DOMAIN, `www.${SITE_DOMAIN}`];

let enabled = false;

const withoutQuery = (url: string): string => {
  try {
    const parsed = new URL(url);
    return `${parsed.origin}${parsed.pathname}`;
  } catch {
    return url.split(/[?#]/)[0];
  }
};

export const trackEvent = (name: string, props?: CustomProperties): void => {
  if (!enabled) return;
  try {
    track(name, { props });
  } catch {
    // Counting a click must never break the click.
  }
};

/** Where on the page a link sits: an explicit data-analytics-place, else its region. */
const placeOf = (link: HTMLElement): string => {
  const tagged = link.closest<HTMLElement>("[data-analytics-place]");
  if (tagged?.dataset.analyticsPlace) return tagged.dataset.analyticsPlace;
  if (link.closest("header")) return "header";
  if (link.closest("footer")) return "footer";
  return "page";
};

const trackLinkClick = (event: MouseEvent): void => {
  const target = event.target;
  if (!(target instanceof Element)) return;
  const link = target.closest<HTMLAnchorElement>("a[href]");
  if (!link) return;

  const href = link.href;
  const place = placeOf(link);

  if (href.startsWith("tel:")) return trackEvent("Call", { place });
  if (href.startsWith("mailto:")) return trackEvent("Email", { place });
  if (/^https:\/\/(wa\.me|api\.whatsapp\.com)\//.test(href)) return trackEvent("WhatsApp", { place });

  try {
    const destination = new URL(href);
    if (destination.origin !== window.location.origin && destination.protocol.startsWith("http")) {
      // Plausible's own name for this goal, so its built-in report picks it up.
      trackEvent("Outbound Link: Click", { url: withoutQuery(href), place });
    }
  } catch {
    // Not a URL we can read; nothing to count.
  }
};

export const initAnalytics = (): boolean => {
  if (!LIVE_HOSTS.includes(window.location.hostname)) return false;

  init({
    domain: SITE_DOMAIN,
    autoCapturePageviews: true,
    logging: false,
    transformRequest: (payload) => ({
      ...payload,
      u: withoutQuery(payload.u),
      r: payload.r ? withoutQuery(payload.r) : payload.r,
    }),
  });
  enabled = true;

  // One listener for every link, so new call and WhatsApp buttons are counted
  // without anyone remembering to tag them.
  document.addEventListener("click", trackLinkClick, { capture: true });
  return true;
};
