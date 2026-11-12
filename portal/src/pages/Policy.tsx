import { useEffect, useState, type FormEvent } from "react";
import {
  ApiError, addBeneficiary, addDependant, fetchPolicy, removeBeneficiary,
  type DependantType, type Instalment, type PolicyDetail,
} from "@/lib/api";
import { dayLabel } from "@/lib/compliance";
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
];

// Someone the policy pays out to who isn't one of its lives, e.g. a brother with
// his own funeral cover. As many details as the main member: the office has to
// be able to find and pay them.
const BLANK_BENEFICIARY = {
  first_names: "", surname: "", relationship: "", id_number: "", date_of_birth: "",
  mobile: "", email: "", address_line1: "", suburb: "", city: "", postal_code: "",
};

const BLANK_DEPENDANT = {
  first_names: "", surname: "", member_type: "child" as DependantType,
  id_number: "", date_of_birth: "", mobile: "",
};

const methodLabel = (code: string) =>
  PAYMENT_METHODS.find((m) => m.value === code)?.label ?? code;

const FREQUENCY_LABELS: Record<string, string> = {
  monthly: "Monthly", quarterly: "Quarterly", annually: "Annually", once_off: "Once-off",
};

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

  const [naming, setNaming] = useState(false);
  const [beneficiary, setBeneficiary] = useState(BLANK_BENEFICIARY);
  const [benBusy, setBenBusy] = useState(false);
  const [benError, setBenError] = useState<string | null>(null);
  const [benErrors, setBenErrors] = useState<Record<string, string>>({});

  const setBen = (key: keyof typeof BLANK_BENEFICIARY) => (value: string) =>
    setBeneficiary((b) => ({ ...b, [key]: value }));
  const orNull = (value: string) => value.trim() || null;

  const benFailed = (err: unknown) => {
    if (err instanceof ApiError) {
      setBenError(err.message);
      setBenErrors(err.fieldErrors);
    } else {
      setBenError("Could not save. Try again.");
    }
  };

  const makeBeneficiary = async (personId: string) => {
    setBenError(null);
    setBenBusy(true);
    try {
      await addBeneficiary(id, { person_id: personId });
      setReload((n) => n + 1);
    } catch (err) {
      benFailed(err);
    } finally {
      setBenBusy(false);
    }
  };

  const submitBeneficiary = async (event: FormEvent) => {
    event.preventDefault();
    setBenError(null);
    setBenErrors({});
    setBenBusy(true);
    try {
      await addBeneficiary(id, {
        person: {
          first_names: beneficiary.first_names.trim(),
          surname: beneficiary.surname.trim(),
          relationship: orNull(beneficiary.relationship),
          id_number: orNull(beneficiary.id_number),
          date_of_birth: beneficiary.date_of_birth || null,
          mobile: orNull(beneficiary.mobile),
          email: orNull(beneficiary.email),
          address_line1: orNull(beneficiary.address_line1),
          suburb: orNull(beneficiary.suburb),
          city: orNull(beneficiary.city),
          postal_code: orNull(beneficiary.postal_code),
        },
      });
      setBeneficiary(BLANK_BENEFICIARY);
      setNaming(false);
      setReload((n) => n + 1);
    } catch (err) {
      benFailed(err);
    } finally {
      setBenBusy(false);
    }
  };

  const unname = async (beneficiaryId: string) => {
    setBenError(null);
    setBenBusy(true);
    try {
      await removeBeneficiary(id, beneficiaryId);
      setReload((n) => n + 1);
    } catch (err) {
      benFailed(err);
    } finally {
      setBenBusy(false);
    }
  };

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
  const beneficiaryIds = new Set(policy.beneficiaries.map((b) => b.person_id));
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

          {policy.notes && (
            <section className="card">
              <div className="card-head"><h2 className="t-section">Notes</h2></div>
              <p className="t-small" style={{ margin: 0, whiteSpace: "pre-wrap" }}>{policy.notes}</p>
            </section>
          )}

          <section className="card" style={{ padding: 0, overflow: "hidden" }}>
            <div className="card-head" style={{ padding: "var(--s24) var(--s24) 0" }}>
              <h2 className="t-section">Lives covered</h2>
            </div>
            {policy.lives.length === 0 ? <Empty title="Nobody on this policy yet" /> : (
              <div className="table-wrap"><table>
                <thead><tr><th>Name</th><th>Role</th><th>ID number</th><th>Date of birth</th><th>Entry age</th><th /></tr></thead>
                <tbody>{policy.lives.map((life) => (
                  <tr key={life.policy_member_id} className="clickable"
                    onClick={() => navigate({ name: "member", id: life.person_id })}>
                    <td className="cell-name">{life.first_names} {life.surname}</td>
                    <td>{life.member_type_label}</td>
                    <td className="ref">{life.id_number ?? <span className="muted">None</span>}</td>
                    <td>{life.date_of_birth ? formatDate(life.date_of_birth) : <span className="muted">Not recorded</span>}</td>
                    <td>{life.entry_age ?? "—"}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      {beneficiaryIds.has(life.person_id)
                        ? <Badge tone="success">Beneficiary</Badge>
                        : canEdit && (
                          <Button small disabled={benBusy}
                            onClick={() => void makeBeneficiary(life.person_id)}>
                            Make beneficiary
                          </Button>
                        )}
                    </td>
                  </tr>
                ))}</tbody>
              </table></div>
            )}
          </section>

          <section className="card">
            <div className="card-head">
              <h2 className="t-section">Beneficiary</h2>
              {canEdit && !naming && (
                <Button small onClick={() => { setNaming(true); setBenError(null); }}>
                  Add someone not on the policy
                </Button>
              )}
            </div>
            <p className="t-small muted" style={{ marginTop: 0 }}>
              Who receives the payout. Choose <strong>Make beneficiary</strong> on one of the lives
              above, or add someone who isn&rsquo;t covered by this policy.
            </p>
            {benError && <div style={{ marginBottom: "var(--s16)" }}>
              <Notice tone="error" title="Not saved." detail={benError} /></div>}
            {policy.beneficiaries.length === 0 && !naming && (
              <Notice tone="warn" title="No beneficiary yet."
                detail="Every policy needs someone to receive the payout." />
            )}
            {policy.beneficiaries.length > 0 && (
              <div className="table-wrap"><table>
                <thead><tr><th>Name</th><th>Relationship</th><th>ID number</th><th>On the policy</th><th /></tr></thead>
                <tbody>{policy.beneficiaries.map((b) => (
                  <tr key={b.beneficiary_id}>
                    <td className="cell-name">{b.first_names} {b.surname}</td>
                    <td>{b.relationship ?? <span className="muted">Not recorded</span>}</td>
                    <td className="ref">{b.id_number ?? <span className="muted">None</span>}</td>
                    <td>{b.covered_life ? "Covered life" : "Not covered"}</td>
                    <td>{canEdit && (
                      <Button small variant="ghost" disabled={benBusy}
                        onClick={() => void unname(b.beneficiary_id)}>Remove</Button>
                    )}</td>
                  </tr>
                ))}</tbody>
              </table></div>
            )}
            {naming && (
              <form className="stack-8" onSubmit={submitBeneficiary} noValidate
                style={{ marginTop: "var(--s16)" }}>
                <div className="form-grid">
                  <Field label="First names" value={beneficiary.first_names}
                    onChange={setBen("first_names")} required
                    error={benErrors["person.first_names"]} autoComplete="off" />
                  <Field label="Surname" value={beneficiary.surname} onChange={setBen("surname")}
                    required error={benErrors["person.surname"]} autoComplete="off" />
                  <Field label="Relationship" value={beneficiary.relationship}
                    onChange={setBen("relationship")} hint="To the main member, e.g. Brother"
                    error={benErrors["person.relationship"]} autoComplete="off" />
                  <Field label="ID number" value={beneficiary.id_number}
                    onChange={setBen("id_number")} hint="Date of birth is read from it"
                    error={benErrors["person.id_number"]} autoComplete="off" />
                  <Field label="Date of birth" type="date" value={beneficiary.date_of_birth}
                    onChange={setBen("date_of_birth")} hint="Needed when there is no ID number"
                    error={benErrors["person.date_of_birth"]} />
                  <Field label="Mobile" type="tel" value={beneficiary.mobile}
                    onChange={setBen("mobile")} error={benErrors["person.mobile"]} autoComplete="off" />
                  <Field label="Email" type="email" value={beneficiary.email}
                    onChange={setBen("email")} hint="Optional" error={benErrors["person.email"]}
                    autoComplete="off" />
                  <Field label="Street address" value={beneficiary.address_line1}
                    onChange={setBen("address_line1")} error={benErrors["person.address_line1"]}
                    autoComplete="off" />
                  <Field label="Suburb or area" value={beneficiary.suburb}
                    onChange={setBen("suburb")} error={benErrors["person.suburb"]} autoComplete="off" />
                  <Field label="City or town" value={beneficiary.city} onChange={setBen("city")}
                    error={benErrors["person.city"]} autoComplete="off" />
                  <Field label="Postal code" value={beneficiary.postal_code}
                    onChange={setBen("postal_code")} error={benErrors["person.postal_code"]}
                    autoComplete="off" />
                </div>
                <div className="row">
                  <Button variant="primary" type="submit" loading={benBusy} loadingLabel="Saving…">
                    Add beneficiary
                  </Button>
                  <Button variant="ghost" onClick={() => setNaming(false)}>Cancel</Button>
                </div>
              </form>
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
                <Fact label="Payment day">{policy.payment.debit_day
                  ? dayLabel(policy.payment.debit_day) : "No fixed day"}</Fact>
                {policy.payment.pay_branch_label && (
                  <Fact label="Pays at">{policy.payment.pay_branch_label}</Fact>
                )}
                <Fact label="Frequency">{FREQUENCY_LABELS[policy.payment.frequency]
                  ?? policy.payment.frequency}</Fact>
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
