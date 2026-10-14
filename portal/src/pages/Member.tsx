import { useEffect, useState } from "react";
import { ApiError, fetchMember, type MemberDetail } from "@/lib/api";
import { navigate } from "@/lib/router";
import { Badge, Button, Empty, Fact, Notice, Skeleton } from "@/components/ui";

const money = (cents: number | null, currency: string) =>
  cents === null ? "Not recorded" : `${currency} ${(cents / 100).toFixed(2)}`;

export default function Member({ id }: { id: string }) {
  const [member, setMember] = useState<MemberDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setMember(null);
    setLoading(true);
    setError(null);
    fetchMember(id)
      .then((result) => { if (!cancelled) setMember(result); })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load this member.");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [id, retry]);

  const back = <Button variant="ghost" onClick={() => navigate({ name: "members" })}>
    Back to members</Button>;

  if (loading) return <div className="page"><div className="page-head">{back}</div>
    <div className="card"><Skeleton rows={7} /></div></div>;
  if (error) return <div className="page"><div className="page-head">{back}</div>
    <Notice tone="error" title="Could not load this member." detail={error}
      action={<Button small onClick={() => setRetry((value) => value + 1)}>Try again</Button>} /></div>;
  if (!member) return <div className="page"><div className="page-head">{back}</div>
    <Empty title="Member not found">This record is no longer in the member book.</Empty></div>;

  return <div className="page">
    <div className="page-head">
      <div className="page-head-text">
        {back}
        <h1 className="t-heading">{member.first_names} {member.surname}</h1>
        <p className="muted">{member.policies.length} {member.policies.length === 1 ? "policy" : "policies"} linked</p>
      </div>
    </div>

    <div className="split">
      <div className="stack">
        <section className="card">
          <div className="card-head"><h2 className="t-section">Identity</h2></div>
          <div className="fact-grid">
            <Fact label="ID number">{member.id_number ?? "Not recorded"}</Fact>
            <Fact label="ID check"><Badge tone={member.id_number_status === "valid" ? "success" : "neutral"}>
              {member.id_number_status.replace(/_/g, " ")}</Badge></Fact>
            <Fact label="Date of birth">{member.date_of_birth ?? "Not recorded"}</Fact>
            <Fact label="Email">{member.email ?? "Not given"}</Fact>
            <Fact label="Phone">{member.phones.length ? member.phones.map((phone) =>
              <div key={phone.number}><a href={`tel:${phone.number}`}>{phone.number}</a>
                <span className="muted"> · {phone.phone_type.replace(/_/g, " ")}</span></div>)
              : "Not recorded"}</Fact>
          </div>
        </section>
        <section className="card">
          <div className="card-head"><h2 className="t-section">Policies</h2></div>
          {member.policies.length === 0 ? <p className="muted">No linked policy.</p>
            : <div className="stack">{member.policies.map((policy) => <div key={policy.policy_number}>
                <strong className="ref">{policy.policy_number}</strong>
                <span className="muted"> · {policy.status_code.replace(/_/g, " ")}
                  {policy.plan_code ? ` · ${policy.plan_code}` : ""}</span>
                <div className="fact-grid" style={{ marginTop: "var(--s12)" }}>
                  <Fact label="Role">{policy.member_type.replace(/_/g, " ")}
                    {policy.is_inferred ? " (inferred from import)" : ""}</Fact>
                  <Fact label="Entry date">{policy.entry_date ?? "Not recorded"}</Fact>
                  <Fact label="Premium">{money(policy.premium_cents, policy.currency)}</Fact>
                  <Fact label="Cover">{money(policy.cover_cents, policy.currency)}</Fact>
                </div>
                <hr className="divider" />
              </div>)}</div>}
        </section>
      </div>
      <aside className="stack">
        <section className="card">
          <div className="card-head"><h2 className="t-section">Record context</h2></div>
          <Fact label="Source">{member.source.startsWith("import:") ? "Imported policy book" : member.source}</Fact>
          {!member.phones.length && <p className="t-small muted">No phone number is recorded for this member yet.</p>}
        </section>
      </aside>
    </div>
  </div>;
}
