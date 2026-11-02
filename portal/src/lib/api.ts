import { getAccessToken } from "./supabase";

const API_BASE = (
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000"
).replace(/\/+$/, "");

export interface EnquiryRow {
  id: string;
  reference: string;
  stage: "lead" | "application";
  status: string;
  first_name: string;
  surname: string;
  mobile_number: string;
  email: string | null;
  city: string | null;
  suburb_or_town: string | null;
  plan_interest: string;
  plan_selected: string | null;
  created_at: string;
}

export interface EnquiryPage {
  rows: EnquiryRow[];
  total: number;
  limit: number;
  offset: number;
}

export class ApiError extends Error {
  readonly status: number;
  /** Per-field messages from a 422, keyed by the request field name. */
  readonly fieldErrors: Record<string, string>;
  constructor(message: string, status: number, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

/** Every admin call carries the staff token; there are no unauthenticated ones. */
const request = async <T>(path: string, params?: URLSearchParams): Promise<T> => {
  const token = await getAccessToken();
  if (!token) throw new ApiError("Your session has ended. Please sign in again.", 401);

  const url = `${API_BASE}${path}${params && [...params].length ? `?${params}` : ""}`;

  let response: Response;
  try {
    response = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  } catch {
    throw new ApiError(
      "Could not reach the server. Check that the API is running.",
      0,
    );
  }

  if (!response.ok) {
    let detail = "Something went wrong.";
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* keep the generic message */
    }
    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as T;
};

/** POST/PATCH counterpart of `request`. Same auth and error handling. */
const mutate = async <T>(path: string, method: "POST" | "PATCH", body: unknown): Promise<T> => {
  const token = await getAccessToken();
  if (!token) throw new ApiError("Your session has ended. Please sign in again.", 401);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError("Could not reach the server.", 0);
  }

  if (!response.ok) {
    let detail = "Something went wrong.";
    let fieldErrors: Record<string, string> = {};
    try {
      const parsed = await response.json();
      if (typeof parsed?.detail === "string") detail = parsed.detail;
      else if (Array.isArray(parsed?.detail) && parsed.detail[0]?.msg) {
        detail = String(parsed.detail[0].msg).replace("Value error, ", "");
      }
      if (parsed?.field_errors && typeof parsed.field_errors === "object") {
        fieldErrors = parsed.field_errors as Record<string, string>;
      }
    } catch {
      /* keep the generic message */
    }
    throw new ApiError(detail, response.status, fieldErrors);
  }

  return (await response.json()) as T;
};

export interface EnquiryQuery {
  search?: string;
  status?: string;
  sort?: "created_at" | "surname" | "status" | "reference";
  descending?: boolean;
  limit?: number;
  offset?: number;
}

export const fetchEnquiries = (query: EnquiryQuery = {}) => {
  const params = new URLSearchParams();
  if (query.search) params.set("search", query.search);
  if (query.status) params.set("status", query.status);
  if (query.sort) params.set("sort", query.sort);
  if (query.descending !== undefined) params.set("descending", String(query.descending));
  params.set("limit", String(query.limit ?? 50));
  params.set("offset", String(query.offset ?? 0));
  return request<EnquiryPage>("/api/admin/enquiries", params);
};

export interface MemberRow {
  id: string;
  surname: string;
  first_names: string;
  email: string | null;
  id_number_status: string;
  created_at: string;
}

export interface MemberPage {
  rows: MemberRow[];
  total: number;
  limit: number;
  offset: number;
}

export interface MemberPolicy {
  policy_id: string;
  policy_number: string;
  status_code: string;
  plan_code: string | null;
  entry_date: string | null;
  premium_cents: number | null;
  cover_cents: number | null;
  currency: string;
  member_type: string;
  entry_age: number | null;
  is_inferred: boolean;
}

export interface MemberDetail extends MemberRow {
  initials: string | null;
  id_number: string | null;
  date_of_birth: string | null;
  source: string;
  phones: { number: string; phone_type: string; is_primary: boolean }[];
  policies: MemberPolicy[];
}

export interface PolicyRow {
  policy_id: string;
  policy_number: string;
  status_code: string;
  status_label: string;
  plan_code: string | null;
  branch_code: string | null;
  entry_date: string | null;
  premium_cents: number | null;
  cover_cents: number | null;
  currency: string;
  main_member_id: string | null;
  main_member_surname: string | null;
  main_member_first_names: string | null;
  lives_covered: number;
}

export const fetchMembers = (query: { search?: string; limit?: number; offset?: number } = {}) => {
  const params = new URLSearchParams();
  if (query.search) params.set("search", query.search);
  params.set("limit", String(query.limit ?? 25));
  params.set("offset", String(query.offset ?? 0));
  return request<MemberPage>("/api/admin/members", params);
};

export const fetchMember = (id: string) =>
  request<MemberDetail>(`/api/admin/members/${encodeURIComponent(id)}`);

export const fetchPolicies = () => request<PolicyRow[]>("/api/admin/policies");

/* ------------------------------------------------- Enquiry, in full --- */

export interface EnquiryDetail extends EnquiryRow {
  province: string | null;
  language_preference: string;
  id_number: string | null;
  date_of_birth: string | null;
  address_line1: string | null;
  address_line2: string | null;
  postal_code: string | null;
  premium_amount_cents: number | null;
  payment_frequency: string | null;
  payment_preference: string | null;
  number_of_dependants: number | null;
  beneficiary_name: string | null;
  beneficiary_relationship: string | null;
  /** Set once the enquiry has been enrolled as a member. */
  person_id: string | null;
}

export const fetchEnquiry = (id: string) =>
  request<EnquiryDetail>(`/api/admin/enquiries/${encodeURIComponent(id)}`);

/* -------------------------------------------------------- Enrolment --- */

export type PaymentMethod =
  | "debit_order" | "stop_order" | "eft" | "cash" | "card" | "easypay" | "payat" | "undecided";

export type DependantType = "spouse" | "child" | "extended" | "beneficiary";

interface PersonIn {
  surname: string;
  first_names: string;
  id_number?: string | null;
  date_of_birth?: string | null;
  gender?: "male" | "female" | "unspecified" | null;
  mobile?: string | null;
  language_preference?: string;
}

export interface EnrolmentIn extends PersonIn {
  enquiry_id?: string | null;
  initials?: string | null;
  email?: string | null;
  address_line1?: string | null;
  address_line2?: string | null;
  suburb?: string | null;
  city?: string | null;
  province?: string | null;
  postal_code?: string | null;
  policy_number: string;
  plan_code?: string | null;
  entry_date?: string | null;
  premium_cents: number;
  cover_cents?: number | null;
  payment_method: PaymentMethod;
  debit_day?: number | null;
  frequency: "monthly" | "once_off";
}

export interface EnrolmentOut {
  person_id: string;
  policy_id: string;
  policy_number: string;
  instalments_scheduled: number;
}

export interface DependantIn extends PersonIn {
  member_type: DependantType;
}

export const fetchNextPolicyNumber = () =>
  request<{ policy_number: string }>("/api/admin/policies/next-number");

export const enrolMember = (body: EnrolmentIn) =>
  mutate<EnrolmentOut>("/api/admin/members", "POST", body);

export const addDependant = (policyId: string, body: DependantIn) =>
  mutate<{ person_id: string; policy_member_id: string; existing_person: boolean }>(
    `/api/admin/policies/${encodeURIComponent(policyId)}/members`, "POST", body);

/* ---------------------------------------------- Policy and premiums --- */

export interface Instalment {
  id: string;
  policy_id: string;
  due_date: string;
  amount_cents: number;
  currency: string;
  status: "due" | "paid" | "waived" | "cancelled";
  paid_at: string | null;
  paid_amount_cents: number | null;
  paid_method: string | null;
  recorded_by: string | null;
  notes: string | null;
}

export interface PolicyLife {
  policy_member_id: string;
  person_id: string;
  surname: string;
  first_names: string;
  id_number: string | null;
  date_of_birth: string | null;
  member_type: string;
  member_type_label: string;
  entry_age: number | null;
  joined_at: string | null;
}

export interface PolicyDetail {
  policy_id: string;
  policy_number: string;
  status_code: string;
  status_label: string;
  plan_code: string | null;
  branch_code: string | null;
  entry_date: string | null;
  premium_cents: number | null;
  cover_cents: number | null;
  currency: string;
  enquiry_id: string | null;
  enquiry_reference: string | null;
  dependants_expected: number | null;
  lives: PolicyLife[];
  payment: { method: string; debit_day: number | null; frequency: string } | null;
  instalments: Instalment[];
}

export interface OutstandingRow {
  instalment_id: string;
  policy_id: string;
  policy_number: string;
  due_date: string;
  amount_cents: number;
  currency: string;
  /** Positive: days late. Zero or negative: not yet late. */
  days_overdue: number;
  main_member_id: string | null;
  main_member_surname: string | null;
  main_member_first_names: string | null;
  main_member_phone: string | null;
}

export const fetchPolicy = (id: string) =>
  request<PolicyDetail>(`/api/admin/policies/${encodeURIComponent(id)}`);

export const fetchOutstanding = (view: "overdue" | "upcoming", days = 7) =>
  request<OutstandingRow[]>("/api/admin/instalments",
    new URLSearchParams({ view, days: String(days) }));

export const recordPayment = (
  id: string, body: { paid_on: string; amount_cents: number; method: PaymentMethod; notes?: string },
) => mutate<Instalment>(`/api/admin/instalments/${encodeURIComponent(id)}/payment`, "POST", body);

export const waiveInstalment = (id: string, reason: string) =>
  mutate<Instalment>(`/api/admin/instalments/${encodeURIComponent(id)}/waive`, "POST", { reason });

export type StaffRole = "viewer" | "admin" | "owner";

export interface StaffIdentity {
  email: string;
  id: string;
  role: StaffRole;
}

export interface StaffMember {
  id: string;
  email: string;
  full_name: string | null;
  role: StaffRole;
  is_active: boolean;
  has_signed_in: boolean;
  invited_by: string | null;
  last_seen_at: string | null;
  created_at: string;
}

export const fetchMe = () => request<StaffIdentity>("/api/admin/me");

export const fetchStaff = () => request<StaffMember[]>("/api/admin/staff");

/** The new row, and whether Supabase emailed them an invitation. */
export interface StaffAdded extends StaffMember {
  invite_sent: boolean;
}

export const inviteStaff = (body: { email: string; full_name?: string; role: StaffRole }) =>
  mutate<StaffAdded>("/api/admin/staff", "POST", body);

export const changeStaffRole = (id: string, role: StaffRole) =>
  mutate<StaffMember>(`/api/admin/staff/${id}/role`, "PATCH", { role });

export const setStaffActive = (id: string, is_active: boolean) =>
  mutate<StaffMember>(`/api/admin/staff/${id}/active`, "PATCH", { is_active });

/* ------------------------------------------------------------- WhatsApp --- */
/* Only escalations: conversations where a family asked the WhatsApp menu for a
   person. Everything else the menu answers on its own and never shows here. */

export interface WhatsAppEscalation {
  id: string;
  status: "open" | "resolved";
  channel: "whatsapp" | "call";
  topic: string;
  topic_label: string;
  urgent: boolean;
  out_of_hours: boolean;
  promised_for: string | null;
  requested_at: string;
  notified_at: string | null;
  first_reply_at: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
  resolution_note: string | null;
  name: string;
  other_number: string;
  profile_name: string | null;
  enquiry_id: string | null;
  enquiry_reference: string | null;
  person_id: string | null;
  member_name: string | null;
  last_inbound_at: string | null;
  /** Free text is allowed until 24 hours after the family last wrote. */
  window_open: boolean;
  /** Messages from the family since staff last wrote. */
  unanswered: number;
}

export interface WhatsAppMessage {
  id: string;
  direction: "inbound" | "outbound";
  /** "family", "menu", "system", or the staff member's email. */
  author: string;
  body: string | null;
  media: { sid: string; content_type: string }[];
  status: string;
  error_code: string | null;
  menu_node: string | null;
  created_at: string;
}

export interface WhatsAppConversation extends WhatsAppEscalation {
  messages: WhatsAppMessage[];
}

export interface WhatsAppSummary {
  open: number;
  urgent: number;
  oldest_requested_at: string | null;
}

export interface WhatsAppTopicCount {
  topic: string;
  label: string;
  count: number;
}

export interface WhatsAppStats {
  days: number;
  conversations: number;
  messages_in: number;
  escalations: number;
  open_escalations: number;
  ratings: number;
  average_rating: number | null;
  top_answers: WhatsAppTopicCount[];
  escalated_topics: WhatsAppTopicCount[];
  recent_feedback: { rating: number | null; comment: string | null; topic_label: string; created_at: string }[];
}

export const fetchWhatsAppSummary = () =>
  request<WhatsAppSummary>("/api/admin/whatsapp/escalations/summary");

export const fetchEscalations = (view: "open" | "resolved") =>
  request<WhatsAppEscalation[]>("/api/admin/whatsapp/escalations", new URLSearchParams({ view }));

export const fetchEscalation = (id: string) =>
  request<WhatsAppConversation>(`/api/admin/whatsapp/escalations/${encodeURIComponent(id)}`);

export const replyToEscalation = (id: string, body: string) =>
  mutate<WhatsAppMessage>(`/api/admin/whatsapp/escalations/${encodeURIComponent(id)}/reply`,
    "POST", { body });

export const resolveEscalation = (id: string, body: { note?: string; ask_rating: boolean }) =>
  mutate<WhatsAppEscalation>(`/api/admin/whatsapp/escalations/${encodeURIComponent(id)}/resolve`,
    "POST", body);

export const fetchWhatsAppStats = (days = 30) =>
  request<WhatsAppStats>("/api/admin/whatsapp/stats", new URLSearchParams({ days: String(days) }));

/** A photo or document a family sent. The API fetches it from Twilio, so the
 *  browser never sees a Twilio address; an <img> can't send the staff token,
 *  so it comes back as a Blob for an object URL. */
export const fetchWhatsAppMedia = async (messageId: string, index: number): Promise<Blob> => {
  const token = await getAccessToken();
  if (!token) throw new ApiError("Your session has ended. Please sign in again.", 401);
  let response: Response;
  try {
    response = await fetch(
      `${API_BASE}/api/admin/whatsapp/messages/${encodeURIComponent(messageId)}/media/${index}`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
  } catch {
    throw new ApiError("Could not reach the server.", 0);
  }
  if (!response.ok) {
    let detail = "Could not open the attachment.";
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* keep the generic message */
    }
    throw new ApiError(detail, response.status);
  }
  return response.blob();
};
