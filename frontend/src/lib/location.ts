/**
 * Where to find us: the head office and the two town branches, in one place.
 *
 * Each branch has a link that hands its address to whichever map app the
 * device has, and an embedded map. The map's branch picker switches between
 * them (components/OfficeMap.tsx).
 *
 * The embed needs no Google API key by default — `output=embed` is the classic
 * keyless Maps iframe. Set `VITE_GOOGLE_MAPS_API_KEY` to switch to the Maps
 * Embed API instead, which gives a cleaner card and a stable quota. That key is
 * public by design (it compiles into the bundle), so restrict it to the
 * Maps Embed API and to the site's HTTP referrers in the Google Cloud console.
 */

export type BranchId = "edendale" | "boshoff" | "langalibalele";

export interface Branch {
  id: BranchId;
  name_en: string;
  name_zu: string;
  /** Shown to a reader, one line per entry. */
  lines: string[];
  /** One line, for anything that needs the whole address. */
  address: string;
  /**
   * What Google is asked to find. The head office searches for its verified
   * Google Business Profile, which pins the premises; its street address alone
   * pinned kwaMadikane, well away from the office (checked 13 Nov 2026). The
   * town branches search by street address, which pins the right block, and
   * their profiles are not verified yet.
   */
  query: string;
  /**
   * Exact premises coordinates, "lat,lng". Blank falls back to the query.
   * To pin it exactly: open Google Maps, right-click the building, copy the
   * pair it shows, and paste it here.
   */
  coords: string;
}

/**
 * The same three branches the portal offers for paying in person
 * (PAY_BRANCHES, migration 0023), in the same order. Addresses as printed on
 * the owner's flyer (12 Nov 2026) and the Google Business Profiles.
 */
export const BRANCHES: Branch[] = [
  {
    id: "edendale",
    name_en: "Edendale (Head Office)",
    name_zu: "Edendale (Ihhovisi Elikhulu)",
    lines: ["Edendale Main Road Kwadaya,", "Pietermaritzburg 3201"],
    address: "Edendale Main Road Kwadaya, Pietermaritzburg 3201",
    query: "Induduzo Funeral Home, Edendale Main Road, Pietermaritzburg",
    coords: "",
  },
  {
    id: "boshoff",
    name_en: "161 Boshoff Street",
    name_zu: "161 Boshoff Street",
    lines: ["Shop 35, 161 Boshoff Street,", "Pietermaritzburg 3201"],
    address: "161 Boshoff Street, Pietermaritzburg 3201",
    query: "161 Boshoff Street, Pietermaritzburg 3201",
    coords: "",
  },
  {
    id: "langalibalele",
    name_en: "171 Langalibalele Street",
    name_zu: "171 Langalibalele Street",
    lines: ["171 Langalibalele Street,", "Pietermaritzburg 3201"],
    address: "171 Langalibalele Street, Pietermaritzburg 3201",
    query: "171 Langalibalele Street, Pietermaritzburg 3201",
    coords: "",
  },
];

export const HEAD_OFFICE = BRANCHES[0];

/** What both the link and the embed are pointed at. */
const query = (branch: Branch) => encodeURIComponent(branch.coords || branch.query);

/** Close enough to read street names, wide enough to place the suburb. */
const zoom = (branch: Branch) => (branch.coords ? 17 : 16);

/**
 * Google's cross-platform maps URL. On Android it opens the Google Maps app (or
 * the app chooser); on iOS it offers Google Maps if installed and Apple Maps
 * otherwise; on desktop it opens maps.google.com. No API key, no SDK.
 */
export const mapLink = (branch: Branch) =>
  `https://www.google.com/maps/search/?api=1&query=${query(branch)}`;

const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;

export const mapEmbedSrc = (branch: Branch) => apiKey
  ? `https://www.google.com/maps/embed/v1/place?key=${apiKey}&q=${query(branch)}&zoom=${zoom(branch)}`
  : `https://www.google.com/maps?q=${query(branch)}&z=${zoom(branch)}&output=embed`;

// The head office, under the names the Contact page already uses.
export const OFFICE_ADDRESS = HEAD_OFFICE.address;
export const OFFICE_ADDRESS_LINES = HEAD_OFFICE.lines;
export const OFFICE_MAP_LINK = mapLink(HEAD_OFFICE);
