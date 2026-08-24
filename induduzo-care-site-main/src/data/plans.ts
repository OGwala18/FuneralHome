export type Lang = "en" | "zu";

export interface Bilingual {
  en: string;
  zu: string;
}

export interface PlanTable {
  title: Bilingual;
  note?: Bilingual;
  columns: Bilingual[];
  rows: string[][];
}

export interface Plan {
  id: string;
  name: Bilingual;
  /** Short coverage label used in the comparison table, e.g. "Edolobheni (City)" */
  coverage: Bilingual;
  /** Who the plan covers, shown under the plan name */
  members: Bilingual;
  /** Headline amount, e.g. "R350" */
  price: string;
  /** Suffix shown next to the amount */
  period: Bilingual;
  /** Prefix the amount with "From" on summary cards */
  priceFrom?: boolean;
  /** Secondary payment route, e.g. "or R300 once-off + R50 p/m" */
  priceAlt?: Bilingual;
  /** One-line summary used on the home page and comparison table */
  summary: Bilingual;
  inclusions: Bilingual[];
  tables?: PlanTable[];
  featured?: boolean;
}

/** Guaranteed payouts apply across every Induduzo plan. */
export const GUARANTEED_PAYOUTS: { amount: string; label: Bilingual }[] = [
  {
    amount: "R1,000",
    label: {
      en: "Guaranteed payout — under 21 years",
      zu: "Imali eqinisekisiwe — abangaphansi kweminyaka engu-21",
    },
  },
  {
    amount: "R2,000",
    label: {
      en: "Guaranteed payout — 21 years and over",
      zu: "Imali eqinisekisiwe — abaneminyaka engu-21 nangaphezulu",
    },
  },
];

/** Conditions that apply to every plan, shown above the plan cards. */
export const PLAN_TERMS: { icon: "clock" | "wallet" | "users" | "heart"; text: Bilingual }[] = [
  {
    icon: "clock",
    text: {
      en: "3-month waiting period on all plans",
      zu: "Isikhathi sokulinda sezinyanga ezi-3 kuzo zonke izinhlelo",
    },
  },
  {
    icon: "wallet",
    text: {
      en: "R50 joining fee for all plans",
      zu: "Imali yokujoyina engu-R50 kuzo zonke izinhlelo",
    },
  },
  {
    icon: "users",
    text: {
      en: "No age limits on Plan A & Plan B",
      zu: "Ayikho imikhawulo yeminyaka kuHlelo A noHlelo B",
    },
  },
  {
    icon: "heart",
    text: {
      en: "Zonke izibongo siyazithatha — all family names are welcome",
      zu: "Zonke izibongo siyazithatha — ayikho imikhawulo yezibongo",
    },
  },
];

const UP_TO_15: Bilingual = {
  en: "Up to 15 family members • No age limits",
  zu: "Kuya ku-15 amalungu omndeni • Ayikho imikhawulo yeminyaka",
};

export const PLANS: Plan[] = [
  {
    id: "plan-a",
    name: { en: "Plan A (Urban)", zu: "Uhlelo A (Edolobheni)" },
    coverage: { en: "Edolobheni (City)", zu: "Edolobheni" },
    members: UP_TO_15,
    price: "R350",
    period: { en: "p/m", zu: "ngenyanga" },
    summary: {
      en: "Full city funeral cover for up to 15 members, including the grave and cemetery equipment.",
      zu: "Ukumbozwa okugcwele kwasedolobheni kumalungu afika ku-15, kufaka umgodi nezinto zemathuna.",
    },
    inclusions: [
      { en: "Casket", zu: "Ibhokisi" },
      { en: "Isiphambano (Cross)", zu: "Isiphambano" },
      { en: "Amakhaza (Mortuary fridge & equipment)", zu: "Amakhaza (nezinto zokugcina)" },
      { en: "Tent (2 poles) & 50 chairs", zu: "Itende (izinsika ezi-2) nezitulo ezingu-50" },
      { en: "Photo frame (A3)", zu: "Isikhungo sesithombe (A3)" },
      { en: "50 funeral programmes", zu: "Izinhlelo zomngcwabo ezingu-50" },
      { en: "Gown", zu: "Ingubo" },
      { en: "Hearse & family car", zu: "I-hearse nemoto yomndeni" },
      { en: "Udokotela (Doctor fees)", zu: "Udokotela (izimali zikadokotela)" },
      { en: "Grave at Ethembeni Cemetery", zu: "Umgodi e-Ethembeni" },
      { en: "Cemetery equipment", zu: "Izinto zemathuna" },
    ],
  },
  {
    id: "plan-b",
    name: { en: "Plan B (Emakhaya)", zu: "Uhlelo B (Emakhaya)" },
    coverage: { en: "Emakhaya (Rural)", zu: "Emakhaya" },
    members: UP_TO_15,
    price: "R250",
    period: { en: "p/m", zu: "ngenyanga" },
    featured: true,
    summary: {
      en: "Full rural funeral cover for up to 15 members, from removal through to the service at home.",
      zu: "Ukumbozwa okugcwele kwasemakhaya kumalungu afika ku-15, kusukela ekususweni kuze kube semcimbini ekhaya.",
    },
    inclusions: [
      { en: "Removal", zu: "Ukususwa" },
      { en: "Amakhaza / Storage", zu: "Amakhaza / Ukugcinwa" },
      { en: "Udokotela (Doctor fees)", zu: "Udokotela (izimali zikadokotela)" },
      { en: "Casket", zu: "Ibhokisi" },
      { en: "Isiphambano (Cross)", zu: "Isiphambano" },
      { en: "Gown", zu: "Ingubo" },
      { en: "Hearse & family car", zu: "I-hearse nemoto yomndeni" },
      { en: "Tent (2 poles) & 50 chairs", zu: "Itende (izinsika ezi-2) nezitulo ezingu-50" },
      { en: "Photo frame (A3)", zu: "Isikhungo sesithombe (A3)" },
      { en: "50 funeral programmes", zu: "Izinhlelo zomngcwabo ezingu-50" },
    ],
  },
  {
    id: "plan-c",
    name: { en: "Plan C (Singles/Couples)", zu: "Uhlelo C (Abangashadile/Izithandani)" },
    coverage: { en: "Single / Couple", zu: "Umuntu oyedwa / Izithandani" },
    members: {
      en: "Single member (21–85) or couple (21–59), priced by age band",
      zu: "Ilungu elilodwa (21–85) noma izithandani (21–59), inani ngokweqembu leminyaka",
    },
    price: "R50",
    period: { en: "p/m", zu: "ngenyanga" },
    priceFrom: true,
    summary: {
      en: "Cover for one person or a couple, with unlimited dependent children under 21 on the couple option.",
      zu: "Ukumbozwa komuntu oyedwa noma izithandani, kufaka izingane ezingenamkhawulo ezingaphansi kweminyaka engu-21 kwinketho yezithandani.",
    },
    tables: [
      {
        title: { en: "Single member", zu: "Ilungu elilodwa" },
        columns: [
          { en: "Age group", zu: "Iqembu leminyaka" },
          { en: "Flat lid", zu: "I-Flat Lid" },
          { en: "Casket", zu: "Ibhokisi" },
        ],
        rows: [
          ["21–45", "R50", "R150"],
          ["46–59", "R60", "R180"],
          ["60–75", "R80", "R200"],
          ["76–85", "R120", "R250"],
        ],
      },
      {
        title: { en: "Couple", zu: "Izithandani" },
        note: {
          en: "Flat lid coffin, plus unlimited dependent children under 21.",
          zu: "Ibhokisi le-flat lid, kanye nezingane ezincikile ezingenamkhawulo ezingaphansi kweminyaka engu-21.",
        },
        columns: [
          { en: "Age group", zu: "Iqembu leminyaka" },
          { en: "Flat lid package", zu: "Iphakethe le-Flat Lid" },
        ],
        rows: [
          ["21–45", "R100"],
          ["46–59", "R200"],
        ],
      },
    ],
    inclusions: [
      { en: "Removal", zu: "Ukususwa" },
      { en: "Amakhaza / Storage", zu: "Amakhaza / Ukugcinwa" },
      { en: "Udokotela (Doctor fees)", zu: "Udokotela (izimali zikadokotela)" },
      { en: "Flat lid or casket (by age band)", zu: "I-flat lid noma ibhokisi (ngokweqembu leminyaka)" },
      { en: "Isiphambano (Cross)", zu: "Isiphambano" },
      { en: "Gown", zu: "Ingubo" },
      { en: "Hearse", zu: "I-hearse" },
      { en: "Tent (2 poles) & 50 chairs", zu: "Itende (izinsika ezi-2) nezitulo ezingu-50" },
      {
        en: "Unlimited dependent children under 21 (couple option)",
        zu: "Izingane ezincikile ezingenamkhawulo ezingaphansi kweminyaka engu-21 (inketho yezithandani)",
      },
    ],
  },
  {
    id: "dome-plan",
    name: { en: "Dome Plan", zu: "Uhlelo lwe-Dome" },
    coverage: { en: "Main member + 14", zu: "Ilungu eliyinhloko + 14" },
    members: {
      en: "Main member plus 14 members — 15 people in total",
      zu: "Ilungu eliyinhloko namalungu angu-14 — abantu abangu-15 sebebonke",
    },
    price: "R400",
    period: { en: "once-off", zu: "kanye kuphela" },
    priceAlt: {
      en: "or R300 once-off + R50 p/m",
      zu: "noma R300 kanye kuphela + R50 ngenyanga",
    },
    summary: {
      en: "Our most complete package — 15 members, two family cars and 100 programmes.",
      zu: "Iphakethe lethu eliphelele kakhulu — amalungu angu-15, izimoto zomndeni ezimbili nezinhlelo ezingu-100.",
    },
    inclusions: [
      { en: "2 x family cars", zu: "Izimoto zomndeni ezi-2" },
      { en: "Hearse", zu: "I-hearse" },
      { en: "Casket", zu: "Ibhokisi" },
      { en: "Isiphambano (Cross)", zu: "Isiphambano" },
      { en: "Amakhaza (Mortuary fridge & equipment)", zu: "Amakhaza (nezinto zokugcina)" },
      { en: "Tent (2 poles)", zu: "Itende (izinsika ezi-2)" },
      { en: "100 funeral programmes", zu: "Izinhlelo zomngcwabo ezingu-100" },
      { en: "Photo frame (A3)", zu: "Isikhungo sesithombe (A3)" },
      { en: "Gown", zu: "Ingubo" },
      { en: "Udokotela (Doctor fees)", zu: "Udokotela (izimali zikadokotela)" },
      { en: "Grave at Ethembeni Cemetery", zu: "Umgodi e-Ethembeni" },
      { en: "Cemetery equipment", zu: "Izinto zemathuna" },
    ],
  },
];

export const getPlan = (id: string): Plan | undefined => PLANS.find((plan) => plan.id === id);
