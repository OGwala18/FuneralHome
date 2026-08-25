/**
 * Client for the two-stage registration flow.
 *
 * Stage 1 posts immediately and returns a server-issued id + reference. That is
 * the whole point of splitting the form: the moment someone gives us their name
 * and number, we own that lead, whether or not they ever finish stage 2.
 *
 * Stage 2 patches the same row. The id is held in sessionStorage so a refresh
 * between steps does not lose the thread, and is cleared once the application
 * is submitted.
 */

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/+$/, "");

const STORAGE_KEY = "induduzo-enquiry";

export type PlanCode = "plan_a" | "plan_b" | "plan_c" | "dome_plan" | "unsure";
export type CoverArea = "edolobheni" | "emakhaya";
export type CoffinOption = "flat_lid" | "casket";
export type LanguageCode = "zu" | "en" | "xh" | "af" | "st" | "other";
export type PaymentFrequency = "monthly" | "once_off";
export type PaymentPreference = "debit_order" | "eft" | "cash" | "card" | "undecided";
export type MaritalStatus =
  | "single"
  | "married"
  | "customary_union"
  | "divorced"
  | "widowed"
  | "other";

/** Stage 1 — what we need to be able to phone someone back. */
export interface LeadPayload {
  first_name: string;
  surname: string;
  mobile_number: string;
  email?: string;
  city?: string;
  suburb_or_town?: string;
  province?: string;
  language_preference: LanguageCode;
  plan_interest: PlanCode;
  best_contact_time?: string;
  how_heard?: string;
  contact_consent: boolean;
  marketing_consent: boolean;
}

/** Stage 2 — everything someone who actually wants cover must provide. */
export interface ApplicationPayload {
  id_number?: string;
  date_of_birth?: string;
  marital_status?: MaritalStatus;
  address_line1?: string;
  address_line2?: string;
  postal_code?: string;
  cover_area?: CoverArea;
  plan_selected?: PlanCode;
  coffin_choice?: CoffinOption;
  age_band?: string;
  premium_amount_cents?: number;
  payment_frequency?: PaymentFrequency;
  payment_preference?: PaymentPreference;
  number_of_dependants?: number;
  next_of_kin_name?: string;
  next_of_kin_mobile?: string;
  next_of_kin_relationship?: string;
  beneficiary_name?: string;
  beneficiary_mobile?: string;
  beneficiary_relationship?: string;
  notes?: string;
  terms_accepted: boolean;
}

export interface EnquiryHandle {
  id: string;
  reference: string;
  first_name: string;
  surname: string;
  mobile_number: string;
  plan_interest: PlanCode;
}

export class RegistrationError extends Error {
  readonly fieldErrors: Record<string, string>;

  constructor(message: string, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.name = "RegistrationError";
    this.fieldErrors = fieldErrors;
  }
}

/** Normalise a South African mobile number to the +27XXXXXXXXX the API expects. */
export const normaliseMobile = (raw: string): string => {
  const digits = raw.replace(/[\s()-]/g, "");
  if (/^0[6-8][0-9]{8}$/.test(digits)) return `+27${digits.slice(1)}`;
  if (/^\+?27[6-8][0-9]{8}$/.test(digits)) return digits.startsWith("+") ? digits : `+${digits}`;
  return digits;
};

export const isValidMobile = (raw: string): boolean =>
  /^\+27[6-8][0-9]{8}$/.test(normaliseMobile(raw));

export const isValidEmail = (raw: string): boolean =>
  raw.trim() === "" || /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(raw.trim());

/**
 * A South African ID is 13 digits and carries a Luhn check digit. Validating it
 * here catches typos before they reach the database, where a bad number would
 * silently become a duplicate-person problem later.
 */
export const isValidSaId = (raw: string): boolean => {
  const digits = raw.replace(/\s/g, "");
  if (!/^[0-9]{13}$/.test(digits)) return false;

  // Date-of-birth portion must be a real date.
  const month = Number(digits.slice(2, 4));
  const day = Number(digits.slice(4, 6));
  if (month < 1 || month > 12 || day < 1 || day > 31) return false;

  // Standard Luhn over the first 12 digits: every second digit counting from
  // the RIGHT of the payload is doubled, i.e. the digit left of the check digit.
  let sum = 0;
  for (let i = 0; i < 12; i += 1) {
    let digit = Number(digits[11 - i]);
    if (i % 2 === 0) {
      digit *= 2;
      if (digit > 9) digit -= 9;
    }
    sum += digit;
  }
  return (10 - (sum % 10)) % 10 === Number(digits[12]);
};

/** Date of birth encoded in a valid SA ID, so we never ask twice. */
export const dobFromSaId = (raw: string): string | undefined => {
  const digits = raw.replace(/\s/g, "");
  if (!isValidSaId(digits)) return undefined;
  const yy = Number(digits.slice(0, 2));
  const century = yy <= Number(String(new Date().getFullYear()).slice(2)) ? 2000 : 1900;
  return `${century + yy}-${digits.slice(2, 4)}-${digits.slice(4, 6)}`;
};

// ---------------------------------------------------------------------------
// Session handoff between the two steps
// ---------------------------------------------------------------------------

export const storeEnquiry = (handle: EnquiryHandle) => {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(handle));
  } catch {
    // Private browsing can refuse storage. The flow still works; the user just
    // cannot refresh between steps without starting over.
  }
};

export const loadEnquiry = (): EnquiryHandle | null => {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as EnquiryHandle) : null;
  } catch {
    return null;
  }
};

export const clearEnquiry = () => {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* no-op */
  }
};

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

const request = async <T,>(path: string, init: RequestInit): Promise<T> => {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init.headers },
    });
  } catch {
    throw new RegistrationError(
      "We could not reach our system just now. Please phone or WhatsApp us and we will capture your details for you.",
    );
  }

  if (!response.ok) {
    let fieldErrors: Record<string, string> = {};
    let message = "Something went wrong on our side. Please try again, or phone us.";
    try {
      const body = await response.json();
      if (body?.detail && typeof body.detail === "string") message = body.detail;
      if (body?.field_errors && typeof body.field_errors === "object") {
        fieldErrors = body.field_errors as Record<string, string>;
      }
    } catch {
      /* keep the generic message */
    }
    throw new RegistrationError(message, fieldErrors);
  }

  return (await response.json()) as T;
};

export const submitLead = (payload: LeadPayload) =>
  request<EnquiryHandle>("/api/enquiries", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const submitApplication = (enquiryId: string, payload: ApplicationPayload) =>
  request<EnquiryHandle>(`/api/enquiries/${enquiryId}/application`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
