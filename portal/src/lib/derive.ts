import type { EnquiryRow } from "./api";

/**
 * Everything the portal shows beyond a raw list is derived here, from rows the
 * API already returned. Nothing in this file invents a number.
 *
 * Why derive rather than ask the server: there is no metrics endpoint and no
 * call-outcome endpoint. Rather than mock one, the portal computes what the
 * enquiry data genuinely supports and says plainly where its figures come from.
 */

/* --------------------------------------------------------------- Labels --- */

export const label = (value: string) =>
  value.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

export const fullName = (row: EnquiryRow) => `${row.first_name} ${row.surname}`.trim();

export const initials = (row: EnquiryRow) =>
  `${row.first_name.charAt(0)}${row.surname.charAt(0)}`.toUpperCase();

export const area = (row: EnquiryRow) =>
  [row.suburb_or_town, row.city].filter(Boolean).join(", ") || "Not given";

/**
 * "plan_a" reads as "Plan A", not "Plan a": the plan letter is a name, not a
 * word. "dome_plan" is left alone, because only a trailing single letter is
 * treated as one.
 */
export const planLabel = (value: string) =>
  label(value).replace(/ ([a-z])$/, (_m, letter: string) => ` ${letter.toUpperCase()}`);

export const planOf = (row: EnquiryRow) => planLabel(row.plan_selected ?? row.plan_interest);

/* ----------------------------------------------------------------- Time --- */

export const formatDate = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-ZA", { day: "2-digit", month: "short", year: "numeric" });
};

export const daysSince = (iso: string): number => {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return 0;
  return Math.max(0, Math.floor((Date.now() - then) / 86_400_000));
};

/** "Today", "Yesterday", "4 days ago" reads faster than a date in a queue. */
export const waitingFor = (iso: string): string => {
  const days = daysSince(iso);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days} days ago`;
  if (days < 14) return "Last week";
  if (days < 60) return `${Math.floor(days / 7)} weeks ago`;
  return `${Math.floor(days / 30)} months ago`;
};

/* ---------------------------------------------------------------- Queue --- */

/**
 * The Today queue, chunked into named groups rather than one flat list
 * (Miller). Order is deliberate: the group that costs the business most sits
 * first, and everything inside a group is oldest first, because the person who
 * has waited longest is the one to phone.
 *
 * "Handled" is anything past first contact. It is derived from `status`, which
 * is the only signal the API gives us; there is no per-call outcome record.
 */

const OPEN_STATUSES = new Set(["new", "contacted"]);

export type QueueTone = "overdue" | "due" | "neutral";

export interface QueueGroup {
  key: string;
  title: string;
  note: string;
  tone: QueueTone;
  rows: EnquiryRow[];
}

export const isHandled = (row: EnquiryRow) => !OPEN_STATUSES.has(row.status);

export const buildQueue = (rows: EnquiryRow[]): QueueGroup[] => {
  const open = rows.filter((r) => !isHandled(r));
  const oldestFirst = [...open].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  );

  const overdue = oldestFirst.filter((r) => r.status === "new" && daysSince(r.created_at) >= 3);
  const waiting = oldestFirst.filter((r) => r.status === "new" && daysSince(r.created_at) < 3);
  const followUp = oldestFirst.filter((r) => r.status === "contacted");

  const groups: QueueGroup[] = [
    {
      key: "overdue",
      title: "Overdue",
      note: "Nobody has called these yet and they have been waiting three days or more.",
      tone: "overdue",
      rows: overdue,
    },
    {
      key: "waiting",
      title: "Waiting for a first call",
      note: "Came in recently. Still the first conversation.",
      tone: "due",
      rows: waiting,
    },
    {
      key: "follow-up",
      title: "Spoken to before",
      note: "Someone has already made contact. Pick up where that left off.",
      tone: "neutral",
      rows: followUp,
    },
  ];

  return groups.filter((group) => group.rows.length > 0);
};

export const queueProgress = (rows: EnquiryRow[]) => {
  const total = rows.length;
  const handled = rows.filter(isHandled).length;
  return { handled, total, percent: total === 0 ? 0 : Math.round((handled / total) * 100) };
};

export const toneForRow = (row: EnquiryRow): QueueTone => {
  if (row.status === "new" && daysSince(row.created_at) >= 3) return "overdue";
  if (row.status === "new") return "due";
  return "neutral";
};

/* --------------------------------------------------------------- Growth --- */

/**
 * Aggregates computed from the rows currently loaded. The caller is expected to
 * say so on screen: with no metrics endpoint, a total here means "of the
 * enquiries fetched", not "of all time", and claiming otherwise would be a lie
 * in a business report.
 */

export interface Tally { key: string; label: string; count: number }

const tally = (
  rows: EnquiryRow[],
  pick: (row: EnquiryRow) => string | null,
  name: (key: string) => string = label,
): Tally[] => {
  const counts = new Map<string, number>();
  for (const row of rows) {
    const key = pick(row);
    if (!key) continue;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([key, count]) => ({ key, label: name(key), count }))
    .sort((a, b) => b.count - a.count);
};

export const byPlan = (rows: EnquiryRow[]) =>
  tally(rows, (r) => r.plan_selected ?? r.plan_interest, planLabel);
export const byArea = (rows: EnquiryRow[]) => tally(rows, (r) => r.suburb_or_town ?? r.city);
export const byStatus = (rows: EnquiryRow[]) => tally(rows, (r) => r.status);

/** Enquiries per day for the last `days` days, oldest first. */
export const perDay = (rows: EnquiryRow[], days = 30): { day: string; count: number }[] => {
  const buckets: { day: string; count: number }[] = [];
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    buckets.push({ day: d.toISOString().slice(0, 10), count: 0 });
  }

  const index = new Map(buckets.map((b, i) => [b.day, i]));
  for (const row of rows) {
    const key = new Date(row.created_at).toISOString().slice(0, 10);
    const at = index.get(key);
    if (at !== undefined) buckets[at].count += 1;
  }
  return buckets;
};

export const conversion = (rows: EnquiryRow[]) => {
  const leads = rows.length;
  const applications = rows.filter((r) => r.stage === "application").length;
  return {
    leads,
    applications,
    percent: leads === 0 ? 0 : Math.round((applications / leads) * 100),
  };
};
