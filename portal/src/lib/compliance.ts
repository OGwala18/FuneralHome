/**
 * The compliance questions asked of a main member at enrolment, and how to
 * read the answers back. The codes match what the API accepts
 * (backend/app/routers/members.py) and what migration 0018 stores.
 */

type Option = { value: string; label: string };

/** ISO 3166 codes. South Africa first, then the region, then further away. */
export const COUNTRIES: Option[] = [
  { value: "ZA", label: "South Africa" },
  { value: "AO", label: "Angola" },
  { value: "BW", label: "Botswana" },
  { value: "BI", label: "Burundi" },
  { value: "CM", label: "Cameroon" },
  { value: "CD", label: "Congo (DRC)" },
  { value: "CG", label: "Congo (Republic)" },
  { value: "SZ", label: "Eswatini" },
  { value: "ET", label: "Ethiopia" },
  { value: "GH", label: "Ghana" },
  { value: "KE", label: "Kenya" },
  { value: "LS", label: "Lesotho" },
  { value: "MG", label: "Madagascar" },
  { value: "MW", label: "Malawi" },
  { value: "MZ", label: "Mozambique" },
  { value: "NA", label: "Namibia" },
  { value: "NG", label: "Nigeria" },
  { value: "RW", label: "Rwanda" },
  { value: "SO", label: "Somalia" },
  { value: "TZ", label: "Tanzania" },
  { value: "UG", label: "Uganda" },
  { value: "ZM", label: "Zambia" },
  { value: "ZW", label: "Zimbabwe" },
  { value: "BD", label: "Bangladesh" },
  { value: "CN", label: "China" },
  { value: "IN", label: "India" },
  { value: "PK", label: "Pakistan" },
  { value: "PT", label: "Portugal" },
  { value: "GB", label: "United Kingdom" },
  // ISO's code for "not known". Rare enough to note on paper.
  { value: "ZZ", label: "Another country" },
];

export const SOUTH_AFRICA = "ZA";

export const EMPLOYMENT_STATUSES: Option[] = [
  { value: "full_time", label: "Full-time employed" },
  { value: "part_time", label: "Part-time employed" },
  { value: "self_employed", label: "Self-employed" },
  { value: "pensioner", label: "Pensioner" },
  { value: "unemployed", label: "Unemployed" },
];

/** Employer, industry, profession and role are asked only of these. */
export const WORKING = new Set(["full_time", "part_time", "self_employed"]);

export const INDUSTRIES: Option[] = [
  { value: "agriculture", label: "Agriculture" },
  { value: "construction", label: "Construction" },
  { value: "domestic_work", label: "Domestic work" },
  { value: "education", label: "Education" },
  { value: "finance", label: "Finance and insurance" },
  { value: "government", label: "Government" },
  { value: "health", label: "Health" },
  { value: "hospitality", label: "Hospitality" },
  { value: "informal_trade", label: "Informal trade" },
  { value: "manufacturing", label: "Manufacturing" },
  { value: "mining", label: "Mining" },
  { value: "retail", label: "Retail" },
  { value: "security", label: "Security" },
  { value: "transport", label: "Transport" },
  { value: "other", label: "Other" },
];

export const JOB_ROLES: Option[] = [
  { value: "manager", label: "Manager" },
  { value: "supervisor", label: "Supervisor" },
  { value: "admin", label: "Admin / clerical" },
  { value: "professional", label: "Professional" },
  { value: "skilled", label: "Skilled / technical" },
  { value: "general_worker", label: "General worker" },
  { value: "owner", label: "Business owner" },
  { value: "other", label: "Other" },
];

export const SOURCES_OF_FUNDS: Option[] = [
  { value: "employment", label: "Employment" },
  { value: "inheritance", label: "Inheritance" },
  { value: "allowance", label: "Allowance" },
  { value: "pension", label: "Pension" },
  { value: "other", label: "Other" },
];

/** "31" is the last day of the month, whatever its length. */
export const dayLabel = (day: number) => (day === 31 ? "Last day of the month" : ordinal(day));

const ordinal = (n: number) => {
  const tens = n % 100;
  if (tens >= 11 && tens <= 13) return `${n}th`;
  return `${n}${({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[n % 10] ?? "th"}`;
};

export const SALARY_DAYS: Option[] = [
  { value: "", label: "Not given" },
  ...Array.from({ length: 30 }, (_, i) => ({ value: String(i + 1), label: ordinal(i + 1) })),
  { value: "31", label: dayLabel(31) },
];

/** The label for a stored code, or the code itself if the list has moved on. */
export const labelFor = (options: Option[], value: string | null) =>
  value === null ? null : options.find((o) => o.value === value)?.label ?? value;
