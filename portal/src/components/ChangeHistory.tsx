import { useEffect, useState } from "react";
import { ApiError, fetchPolicyHistory, type HistoryEntry } from "@/lib/api";
import { Button, Notice, Skeleton } from "@/components/ui";

/**
 * What a policy and its main member's record used to say: every change, its
 * old and new value, who made it and when. Read from member_book_history,
 * which the database writes itself (migration 0031), so nothing that changes
 * the book can leave it out.
 */

const RECORDS: Record<string, string> = {
  people: "Member details",
  person_phones: "Phone number",
  addresses: "Address",
  policies: "Policy",
  policy_payments: "How they pay",
  policy_members: "Life on the policy",
  policy_beneficiaries: "Beneficiary",
  premium_instalments: "Premium",
};

const FIELDS: Record<string, string> = {
  first_names: "First names", surname: "Surname", initials: "Initials",
  id_number: "ID number", id_number_status: "ID check", date_of_birth: "Date of birth",
  date_of_birth_source: "Date of birth from", gender: "Gender", email: "Email",
  language_preference: "Language", country_of_birth: "Country of birth",
  citizenship: "Citizenship", passport_number: "Passport number",
  employment_status: "Employment", employer_name: "Employer", industry: "Industry",
  occupation: "Profession", job_role: "Role", source_of_funds: "Source of funds",
  source_of_funds_other: "Other source of funds", salary_day: "Salary day",
  number: "Number", is_primary: "Main number", is_whatsapp: "On WhatsApp",
  archived_at: "Removed", line1: "Street address", line2: "Address line 2",
  suburb: "Suburb", city: "City", province: "Province", postal_code: "Postal code",
  policy_number: "Policy number", status_code: "Status", plan_code: "Plan",
  plan_option: "Plan option", entry_date: "Start date", premium_cents: "Premium",
  cover_cents: "Cover", notes: "Notes", method: "Method", debit_day: "Payment day",
  frequency: "Frequency", pay_branch_code: "Pays at", member_type: "Role",
  status: "Status", amount_cents: "Amount", due_date: "Due", recorded_by: "Recorded by",
  relationship: "Relationship", share_percent: "Share",
};

const VERBS = { insert: "added", update: "changed", delete: "removed" } as const;

const show = (field: string, value: string | null) => {
  if (value === null || value === "") return <span className="muted">empty</span>;
  if (field.endsWith("_cents") && /^\d+$/.test(value)) {
    return `R ${(Number(value) / 100).toFixed(2)}`;
  }
  if (field === "archived_at") return new Date(value).toLocaleString("en-ZA");
  // Codes ("plan_b", "full_time") read as words; typed text is left as typed.
  return /^[a-z_]+$/.test(value) ? value.replace(/_/g, " ") : value;
};

const SHOWN = 20;

export default function ChangeHistory({ policyId, version = 0 }: { policyId: string; version?: number }) {
  const [entries, setEntries] = useState<HistoryEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [all, setAll] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    fetchPolicyHistory(policyId)
      .then((rows) => { if (!cancelled) setEntries(rows); })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load the history.");
      });
    return () => { cancelled = true; };
  }, [policyId, version]);

  const visible = entries ? (all ? entries : entries.slice(0, SHOWN)) : [];

  return (
    <section className="card">
      <div className="card-head"><h2 className="t-section">Change history</h2></div>
      <p className="t-small muted" style={{ marginTop: 0 }}>
        Every change to this member and policy, newest first, with what it used to be.
        If a correction was wrong, the old value is here to put back.
      </p>
      {error && <Notice tone="error" title="Could not load the history." detail={error} />}
      {!error && entries === null && <Skeleton rows={4} />}
      {entries !== null && entries.length === 0 && (
        <p className="muted">No changes recorded yet. History starts from 16 Nov 2026.</p>
      )}
      {visible.length > 0 && (
        <div className="stack">
          {visible.map((entry, index) => (
            <div key={`${entry.changed_at}-${index}`}>
              <div className="t-small">
                <strong>{RECORDS[entry.table_name] ?? entry.table_name} {VERBS[entry.operation]}</strong>
                <span className="muted"> · {new Date(entry.changed_at).toLocaleString("en-ZA")}
                  {" · "}{entry.changed_by}</span>
              </div>
              {entry.operation === "update" && entry.changes.length > 0 && (
                <div className="table-wrap" style={{ marginTop: "var(--s8)" }}><table>
                  <thead><tr><th>Field</th><th>Was</th><th>Now</th></tr></thead>
                  <tbody>{entry.changes.map((change) => (
                    <tr key={change.field}>
                      <td>{FIELDS[change.field] ?? change.field.replace(/_/g, " ")}</td>
                      <td>{show(change.field, change.old)}</td>
                      <td>{show(change.field, change.new)}</td>
                    </tr>
                  ))}</tbody>
                </table></div>
              )}
            </div>
          ))}
          {entries && entries.length > SHOWN && (
            <Button small variant="ghost" onClick={() => setAll((v) => !v)}>
              {all ? "Show fewer" : `Show all ${entries.length}`}
            </Button>
          )}
        </div>
      )}
    </section>
  );
}
