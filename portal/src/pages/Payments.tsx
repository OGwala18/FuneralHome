import { useEffect, useState } from "react";
import { ApiError, fetchOutstanding, type OutstandingRow } from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/derive";
import { navigate } from "@/lib/router";
import PaymentForm from "@/components/PaymentForm";
import { Badge, Button, Empty, Notice, Skeleton } from "@/components/ui";

/**
 * Premiums owed, in the two lists the office works from: who is late, and who
 * falls due this week. The same rows will drive WhatsApp reminders once those
 * are approved; until then this is the list to phone from.
 */

const UPCOMING_DAYS = 7;

function OutstandingTable({ rows, canEdit, late, onChanged }: {
  rows: OutstandingRow[]; canEdit: boolean; late: boolean; onChanged: () => void;
}) {
  const [paying, setPaying] = useState<string | null>(null);

  return (
    <div className="table-wrap"><table>
      <thead><tr><th>Policy</th><th>Main member</th><th>Phone</th><th>Due</th><th>Amount</th>
        <th>{late ? "Late by" : "Due in"}</th><th /></tr></thead>
      <tbody>{rows.map((row) => (
        paying === row.instalment_id ? (
          <tr key={row.instalment_id}><td colSpan={7}>
            <PaymentForm instalmentId={row.instalment_id} amountCents={row.amount_cents}
              currency={row.currency} onCancel={() => setPaying(null)}
              onDone={() => { setPaying(null); onChanged(); }} />
          </td></tr>
        ) : (
          <tr key={row.instalment_id}>
            <td><Button variant="ghost" small
              onClick={() => navigate({ name: "policy", id: row.policy_id })}>
              <span className="ref">{row.policy_number}</span></Button></td>
            <td>{row.main_member_id
              ? <Button variant="ghost" small onClick={() => navigate({ name: "member", id: row.main_member_id! })}>
                  {row.main_member_first_names} {row.main_member_surname}</Button>
              : <span className="muted">Not recorded</span>}</td>
            <td>{row.main_member_phone
              ? <a href={`tel:${row.main_member_phone}`}>{row.main_member_phone}</a>
              : <span className="muted">No number</span>}</td>
            <td>{formatDate(row.due_date)}</td>
            <td>{formatMoney(row.amount_cents, row.currency)}</td>
            <td>{late
              ? <Badge tone="overdue">{row.days_overdue} {row.days_overdue === 1 ? "day" : "days"}</Badge>
              : <Badge tone="due">{row.days_overdue === 0 ? "Today"
                  : `${-row.days_overdue} ${row.days_overdue === -1 ? "day" : "days"}`}</Badge>}</td>
            <td>{canEdit && <Button small onClick={() => setPaying(row.instalment_id)}>Record</Button>}</td>
          </tr>
        )
      ))}</tbody>
    </table></div>
  );
}

export default function Payments({ canEdit }: { canEdit: boolean }) {
  const [overdue, setOverdue] = useState<OutstandingRow[]>([]);
  const [upcoming, setUpcoming] = useState<OutstandingRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([fetchOutstanding("overdue"), fetchOutstanding("upcoming", UPCOMING_DAYS)])
      .then(([late, soon]) => {
        if (cancelled) return;
        setOverdue(late);
        setUpcoming(soon);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load payments.");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [reload]);

  const owed = overdue.reduce((sum, row) => sum + row.amount_cents, 0);

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-text">
          <h1 className="t-heading">Payments</h1>
          <p className="muted">
            {loading && !overdue.length && !upcoming.length ? "Loading premiums…"
              : `${overdue.length} overdue (${formatMoney(owed)}) · ${upcoming.length} due in the next ${UPCOMING_DAYS} days`}
          </p>
        </div>
      </div>

      {error && <Notice tone="error" title="Could not load payments." detail={error}
        action={<Button small onClick={() => setReload((n) => n + 1)}>Try again</Button>} />}

      <div className="stack">
        <section className="card" style={{ padding: 0, overflow: "hidden" }}>
          <div className="card-head" style={{ padding: "var(--s24) var(--s24) 0" }}>
            <h2 className="t-section">Overdue</h2>
          </div>
          {loading && !overdue.length ? <div style={{ padding: "var(--s24)" }}><Skeleton rows={4} /></div>
            : overdue.length === 0 ? <Empty title="Nobody is behind">Every premium due so far is paid or waived.</Empty>
            : <OutstandingTable rows={overdue} canEdit={canEdit} late onChanged={() => setReload((n) => n + 1)} />}
        </section>

        <section className="card" style={{ padding: 0, overflow: "hidden" }}>
          <div className="card-head" style={{ padding: "var(--s24) var(--s24) 0" }}>
            <h2 className="t-section">Due in the next {UPCOMING_DAYS} days</h2>
          </div>
          {loading && !upcoming.length ? <div style={{ padding: "var(--s24)" }}><Skeleton rows={4} /></div>
            : upcoming.length === 0 ? <Empty title="Nothing due this week" />
            : <OutstandingTable rows={upcoming} canEdit={canEdit} late={false} onChanged={() => setReload((n) => n + 1)} />}
        </section>
      </div>
    </div>
  );
}
