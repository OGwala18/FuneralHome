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
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
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
    try {
      const parsed = await response.json();
      if (typeof parsed?.detail === "string") detail = parsed.detail;
      else if (Array.isArray(parsed?.detail) && parsed.detail[0]?.msg) {
        detail = String(parsed.detail[0].msg).replace("Value error, ", "");
      }
    } catch {
      /* keep the generic message */
    }
    throw new ApiError(detail, response.status);
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

export const inviteStaff = (body: { email: string; full_name?: string; role: StaffRole }) =>
  mutate<StaffMember>("/api/admin/staff", "POST", body);

export const changeStaffRole = (id: string, role: StaffRole) =>
  mutate<StaffMember>(`/api/admin/staff/${id}/role`, "PATCH", { role });

export const setStaffActive = (id: string, is_active: boolean) =>
  mutate<StaffMember>(`/api/admin/staff/${id}/active`, "PATCH", { is_active });
