import { useEffect, useState } from "react";
import { ApiError, fetchPolicies, type PolicyRow } from "@/lib/api";
import { navigate } from "@/lib/router";
import { Badge, Button, Empty, Notice, Skeleton } from "@/components/ui";

const money = (cents: number | null, currency: string) =>
  cents === null ? "Not recorded" : `${currency} ${(cents / 100).toFixed(2)}`;

export default function Policies() {
  const [rows, setRows] = useState<PolicyRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchPolicies()
      .then((result) => { if (!cancelled) setRows(result); })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load policies.");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [retry]);

  return <div className="page">
    <div className="page-head"><div className="page-head-text">
      <h1 className="t-heading">Policies</h1>
      <p className="muted">{loading && rows.length === 0 ? "Loading policies…"
        : `${rows.length} policies in the imported book.`}</p>
    </div></div>
    {error && <Notice tone="error" title="Could not load policies." detail={error}
      action={<Button small onClick={() => setRetry((value) => value + 1)}>Try again</Button>} />}
    <div className="card" style={{ padding: 0, overflow: "hidden" }}>
      {loading && rows.length === 0 ? <div style={{ padding: "var(--s24)" }}><Skeleton rows={8} /></div>
        : rows.length === 0 ? <Empty title="No policies found">The policy book has no records yet.</Empty>
        : <div className="table-wrap"><table>
          <thead><tr><th>Policy</th><th>Main member</th><th>Plan</th><th>Status</th>
            <th>Lives</th><th>Premium</th></tr></thead>
          <tbody>{rows.map((row) => <tr key={row.policy_id}>
            <td className="ref">{row.policy_number}</td>
            <td>{row.main_member_id ? <Button variant="ghost" small
              onClick={() => navigate({ name: "member", id: row.main_member_id! })}>
                {row.main_member_first_names} {row.main_member_surname}</Button>
              : <span className="muted">Not recorded</span>}</td>
            <td>{row.plan_code ?? "Not recorded"}</td>
            <td><Badge tone={row.status_code === "active" ? "success" : "neutral"}>
              {row.status_label}</Badge></td>
            <td>{row.lives_covered}</td>
            <td>{money(row.premium_cents, row.currency)}</td>
          </tr>)}</tbody>
        </table></div>}
    </div>
  </div>;
}
