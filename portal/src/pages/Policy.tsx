import { useEffect, useState, type FormEvent } from "react";
import {
  ApiError, addDependant, fetchPolicy, type DependantType, type Instalment, type PolicyDetail,
} from "@/lib/api";
import { formatDate, formatMoney, planLabel } from "@/lib/derive";
import { navigate } from "@/lib/router";
import PaymentForm, { PAYMENT_METHODS, today } from "@/components/PaymentForm";
import { Badge, Button, Empty, Fact, Field, Notice, Select, Skeleton } from "@/components/ui";

/**
 * One policy: the lives it covers, how it is paid, and every premium owed.
 *
 * Opened straight after enrolment with the dependant form already showing,
 * because the next job after enrolling a family is adding the rest of it.
 */

const DEPENDANT_TYPES: { value: DependantType; label: string }[] = [
  { value: "spouse", label: "Spouse" },
  { value: "child", label: "Child" },
  { value: "extended", label: "Extended family" },
  { value: "beneficiary", label: "Beneficiary" },
];

const BLANK_DEPENDANT = {
  first_names: "", surname: "", member_type: "child" as DependantType,
  id_number: "", date_of_birth: "", mobile: "",
};

const methodLabel = (code: string) =>
  PAYMENT_METHODS.find((m) => m.value === code)?.label ?? code;

const instalmentBadge = (row: Instalment) => {
  if (row.status === "paid") return <Badge tone="success">Paid</Badge>;
  if (row.status === "waived") return <Badge tone="neutral">Waived</Badge>;
  if (row.status === "cancelled") return <Badge tone="neutral">Cancelled</Badge>;
  return row.due_date < today() ? <Badge tone="overdue">Overdue</Badge> : <Badge tone="due">Due</Badge>;
};

export default function Policy({ id, canEdit, addLives }:
  { id: string; canEdit: boolean; addLives?: boolean }) {
  const [policy, setPolicy] = useState<PolicyDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  const [adding, setAdding] = useState(Boolean(addLives) && canEdit);
  const [dependant, setDependant] = useState(BLANK_DEPENDANT);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [added, setAdded] = useState<string | null>(null);

  const [paying, setPaying] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchPolicy(id)
      .then((result) => { if (!cancelled) setPolicy(result); })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load this policy.");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [id, reload]);

  const set = (key: keyof typeof BLANK_DEPENDANT) => (value: string) =>
    setDependant((d) => ({ ...d, [key]: value }));

  const submitDependant = async (event: FormEvent) => {
    event.preventDefault();
    setFormError(null);
    setFieldErrors({});
    setAdded(null);
    setSaving(true);
    try {
      const result = await addDependant(id, {
        first_names: dependant.first_names.trim(),
        surname: dependant.surname.trim(),
        member_type: dependant.member_type,
        id_number: dependant.id_number.trim() || null,
        date_of_birth: dependant.date_of_birth || null,
        mobile: dependant.mobile.trim() || null,
      });
      setAdded(`${dependant.first_names.trim()} ${dependant.surname.trim()} was added`
        + (result.existing_person ? ". They were already in the member book, so their existing record was linked." : "."));
      // Most families share a surname: keep it for the next person.
      setDependant({ ...BLANK_DEPENDANT, surname: dependant.surname });
      setReload((n) => n + 1);
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(err.fieldErrors);
        setFormError(err.message);
      } else {
        setFormError("Could not save. Try again.");
      }
    } finally {
      setSaving(false);
    }
  };

  const back = <Button variant="ghost" onClick={() => navigate({ name: "policies" })}>Back to policies</Button>;

  if (loading && !policy) {
    return <div className="page"><div className="page-head">{back}</div>
      <div className="card"><Skeleton rows={8} /></div></div>;
  }
  if (error || !policy) {
    return <div className="page"><div className="page-head">{back}</div>
      <Notice tone="error" title="Could not load this policy." detail={error ?? "It may have been removed."}
        action={<Button small onClick={() => setReload((n) => n + 1)}>Try again</Button>} /></div>;
  }

  const main = policy.lives.find((life) => life.member_type === "main_member");
  const dependants = policy.lives.length - (main ? 1 : 0);
  const due = policy.instalments.filter((row) => row.status === "due");
  const overdue = due.filter((row) => row.due_date < today());

  return (
    <div className="page">
      <div className="row" style={{ marginBottom: "var(--s16)" }}>
        {back}
        <Badge tone={policy.status_code === "active" ? "success" : "neutral"}>{policy.status_label}</Badge>
      </div>

      <div className="page-head">
        <div className="page-head-text">
          <h1 className="t-heading">
            {policy.policy_number}{main ? ` · ${main.first_names} ${main.surname}` : ""}</h1>
          <p className="muted">
            {policy.plan_code ? planLabel(policy.plan_code) : "No plan recorded"} · {policy.lives.length}{" "}
            {policy.lives.length === 1 ? "life" : "lives"} covered
            {policy.entry_date ? ` · started ${formatDate(policy.entry_date)}` : ""}
            {policy.enquiry_reference && <> · from enquiry <span className="ref">{policy.enquiry_reference}</span></>}
          </p>
        </div>
        {canEdit && !adding && (
          <Button variant="primary" onClick={() => { setAdding(true); setAdded(null); }}>Add dependant</Button>
        )}
      </div>

      {policy.status_code === "pending" && (
        <div style={{ marginBottom: "var(--s16)" }}>
          <Notice tone="warn" title="Waiting for the first premium."
            detail="The policy becomes active when the first instalment below is recorded as paid." />
        </div>
      )}

      <div className="split">
        <div className="stack">
          {adding && (
            <section className="card">
              <div className="card-head">
                <h2 className="t-section">Add a dependant</h2>
                <Button small variant="ghost" onClick={() => setAdding(false)}>Done</Button>
              </div>
              {policy.dependants_expected !== null && (
                <p className="t-small muted" style={{ marginTop: 0 }}>
                  The application listed {policy.dependants_expected}{" "}
                  {policy.dependants_expected === 1 ? "dependant" : "dependants"}; {dependants} added so far.
                </p>
              )}
              {added && <div style={{ marginBottom: "var(--s16)" }}>
                <Notice tone="success" title={added} detail="Add the next person, or choose Done." /></div>}
              {formError && <div style={{ marginBottom: "var(--s16)" }}>
                <Notice tone="error" title="Not added." detail={formError} /></div>}
              <form className="stack-8" onSubmit={submitDependant} noValidate>
                <div className="form-grid">
                  <Field label="First names" value={dependant.first_names} onChange={set("first_names")}
                    required error={fieldErrors.first_names} autoComplete="off" />
                  <Field label="Surname" value={dependant.surname} onChange={set("surname")}
                    required error={fieldErrors.surname} autoComplete="off" />
                  <Select label="Role on the policy" value={dependant.member_type}
                    onChange={set("member_type")} options={DEPENDANT_TYPES} error={fieldErrors.member_type} />
                  <Field label="ID number" value={dependant.id_number} onChange={set("id_number")}
                    hint="If they have one" error={fieldErrors.id_number} autoComplete="off" />
                  <Field label="Date of birth" type="date" value={dependant.date_of_birth}
                    onChange={set("date_of_birth")} hint="Needed when there is no ID number"
                    error={fieldErrors.date_of_birth} />
                  <Field label="Mobile" type="tel" value={dependant.mobile} onChange={set("mobile")}
                    hint="Optional" error={fieldErrors.mobile} autoComplete="off" />
                </div>
                <div className="row">
                  <Button variant="primary" type="submit" loading={saving} loadingLabel="Adding…">
                    Add to policy
                  </Button>
                </div>
              </form>
            </section>
          )}

          <section className="card" style={{ padding: 0, overflow: "hidden" }}>
            <div className="card-head" style={{ padding: "var(--s24) var(--s24) 0" }}>
              <h2 className="t-section">Lives covered</h2>
            </div>
            {policy.lives.length === 0 ? <Empty title="Nobody on this policy yet" /> : (
              <div className="table-wrap"><table>
                <thead><tr><th>Name</th><th>Role</th><th>ID number</th><th>Date of birth</th><th>Entry age</th></tr></thead>
                <tbody>{policy.lives.map((life) => (
                  <tr key={life.policy_member_id} className="clickable"
                    onClick={() => navigate({ name: "member", id: life.person_id })}>
                    <td className="cell-name">{life.first_names} {life.surname}</td>
                    <td>{life.member_type_label}</td>
                    <td className="ref">{life.id_number ?? <span className="muted">None</span>}</td>
                    <td>{life.date_of_birth ? formatDate(life.date_of_birth) : <span className="muted">Not recorded</span>}</td>
                    <td>{life.entry_age ?? "—"}</td>
                  </tr>
                ))}</tbody>
              </table></div>
            )}
          </section>

          <section className="card" style={{ padding: 0, overflow: "hidden" }}>
            <div className="card-head" style={{ padding: "var(--s24) var(--s24) 0" }}>
              <h2 className="t-section">Premium schedule</h2>
              <span className="t-small muted">{due.length} due · {overdue.length} overdue</span>
            </div>
            {policy.instalments.length === 0 ? (
              <Empty title="No instalments scheduled">
                A schedule is created when the policy has a premium recorded.
              </Empty>
            ) : (
              <div className="table-wrap"><table>
                <thead><tr><th>Due</th><th>Amount</th><th>Status</th><th>Paid</th><th /></tr></thead>
                <tbody>{policy.instalments.map((row) => (
                  paying === row.id ? (
                    <tr key={row.id}><td colSpan={5}>
                      <PaymentForm instalmentId={row.id} amountCents={row.amount_cents} currency={row.currency}
                        defaultMethod={policy.payment?.method}
                        onCancel={() => setPaying(null)}
                        onDone={() => { setPaying(null); setReload((n) => n + 1); }} />
                    </td></tr>
                  ) : (
                    <tr key={row.id}>
                      <td>{formatDate(row.due_date)}</td>
                      <td>{formatMoney(row.amount_cents, row.currency)}</td>
                      <td>{instalmentBadge(row)}</td>
                      <td className="t-small muted">
                        {row.status === "paid" && row.paid_at
                          ? `${formatDate(row.paid_at)} · ${methodLabel(row.paid_method ?? "")}`
                          : row.status === "waived" ? row.notes ?? "" : ""}
                      </td>
                      <td>{canEdit && row.status === "due" && (
                        <Button small onClick={() => setPaying(row.id)}>Record</Button>
                      )}</td>
                    </tr>
                  )
                ))}</tbody>
              </table></div>
            )}
          </section>
        </div>

        <aside className="stack">
          <section className="card">
            <div className="card-head"><h2 className="t-section">Cover and payment</h2></div>
            <div className="stack-8">
              <Fact label="Premium">{formatMoney(policy.premium_cents, policy.currency)}</Fact>
              <Fact label="Cover">{formatMoney(policy.cover_cents, policy.currency)}</Fact>
              <hr className="divider" />
              {policy.payment ? <>
                <Fact label="Method">{methodLabel(policy.payment.method)}</Fact>
                <Fact label="Debit day">{policy.payment.debit_day ?? "No fixed day"}</Fact>
                <Fact label="Frequency">{policy.payment.frequency === "once_off" ? "Once-off" : "Monthly"}</Fact>
              </> : <p className="t-small muted" style={{ margin: 0 }}>No payment arrangement recorded.</p>}
            </div>
          </section>
          {main && (
            <section className="card">
              <div className="card-head"><h2 className="t-section">Main member</h2></div>
              <Button onClick={() => navigate({ name: "member", id: main.person_id })}>
                Open {main.first_names}'s record
              </Button>
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}
