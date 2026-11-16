import { useEffect, useState, type FormEvent } from "react";
import {
  ApiError, changePlan, fetchMemberForEdit, fetchPlanPrices,
  type Frequency, type MemberEdit, type PlanPrice,
} from "@/lib/api";
import { formatMoney, planLabel } from "@/lib/derive";
import { navigate } from "@/lib/router";
import { today } from "@/components/PaymentForm";
import {
  FREQUENCIES, ONCE_OFF, PAYMENT_DAYS, PER, PLANS, quote, usePlanOptions,
} from "@/components/MemberForm";
import { Button, Fact, Notice, Select, Skeleton } from "@/components/ui";

/**
 * Move a family to another plan, option or frequency without enrolling them
 * again. The person, the policy number, the dependants, the beneficiary and
 * every payment already made stay exactly as they are.
 *
 * The new premium and cover come from the price list at the main member's age
 * today, as at enrolment. Premiums already paid or already overdue keep the
 * amount they were owed at; the ones still to come are replaced at the new
 * amount. The old plan and price are kept in the change history.
 */

export default function ChangePlan({ policyId }: { policyId: string }) {
  const [record, setRecord] = useState<MemberEdit | null>(null);
  const [prices, setPrices] = useState<PlanPrice[]>([]);
  const [plan, setPlan] = useState({ plan_code: "", plan_option: "", frequency: "monthly" as Frequency,
    payment_day: "" });
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchMemberForEdit(policyId), fetchPlanPrices()])
      .then(([found, priceList]) => {
        if (cancelled) return;
        setRecord(found);
        setPrices(priceList);
        setPlan({
          plan_code: found.plan_code ?? "",
          plan_option: found.plan_option ?? "",
          frequency: found.frequency ?? "monthly",
          payment_day: found.debit_day ? String(found.debit_day) : "",
        });
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof ApiError ? err.message : "Could not load this policy.");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [policyId]);

  const planOptions = usePlanOptions(prices, plan.plan_code);
  const onceOff = prices.some((p) => p.plan_code === plan.plan_code && p.billing === "once_off");

  const back = <Button variant="ghost" onClick={() => navigate({ name: "policy", id: policyId })}>
    Back to policy</Button>;

  if (loading) {
    return <div className="page"><div className="page-head">{back}</div>
      <div className="card"><Skeleton rows={6} /></div></div>;
  }
  if (loadError || !record) {
    return <div className="page"><div className="page-head">{back}</div>
      <Notice tone="error" title="Could not open this policy." detail={loadError ?? "It may have been removed."} /></div>;
  }

  const live = record.status_code === "pending" || record.status_code === "active";
  const on = record.entry_date && record.entry_date > today() ? record.entry_date : today();
  const premium = quote(prices, plan, record.date_of_birth ?? "", on);
  const currentFrequency = (record.frequency ?? "monthly") as Frequency;
  const optionLabel = (code: string | null, option: string | null) =>
    prices.find((p) => p.plan_code === code && p.option_code === option)?.option_label ?? option;
  const unchanged = "cents" in premium && plan.plan_code === record.plan_code
    && (planOptions.length <= 1 || plan.plan_option === record.plan_option)
    && plan.frequency === currentFrequency && premium.cents === record.premium_cents;
  const needsDay = !onceOff && !plan.payment_day;

  const choosePlan = (code: string) => setPlan((p) => {
    const isOnceOff = prices.some((row) => row.plan_code === code && row.billing === "once_off");
    return {
      ...p, plan_code: code, plan_option: "",
      frequency: isOnceOff ? "once_off" : p.frequency === "once_off" ? "monthly" : p.frequency,
    };
  });

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    if (needsDay) {
      setErrors({ debit_day: "Choose the payment day" });
      return;
    }
    setErrors({});
    setSaving(true);
    try {
      await changePlan(policyId, {
        plan_code: plan.plan_code,
        plan_option: plan.plan_option || null,
        frequency: onceOff ? "once_off" : plan.frequency,
        debit_day: !onceOff && plan.payment_day ? Number(plan.payment_day) : null,
      });
      navigate({ name: "policy", id: policyId });
    } catch (e) {
      if (e instanceof ApiError) {
        setErrors(e.fieldErrors);
        setError(e.message);
      } else {
        setError("Could not change the plan. Try again.");
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="page">
      <div className="row" style={{ marginBottom: "var(--s16)" }}>{back}</div>
      <div className="page-head">
        <div className="page-head-text">
          <h1 className="t-heading">Change plan for {record.first_names} {record.surname}</h1>
          <p className="muted">
            Policy <span className="ref">{record.policy_number}</span> keeps its number, its
            dependants, its beneficiary and every payment already made. Only the plan and the
            premiums still to come change.
          </p>
        </div>
      </div>

      {!live && <div style={{ marginBottom: "var(--s16)" }}>
        <Notice tone="warn" title={`This policy is ${record.status_label.toLowerCase()}.`}
          detail="Only a pending or active policy can change plan." /></div>}
      {error && <div style={{ marginBottom: "var(--s16)" }}>
        <Notice tone="error" title="Not changed yet." detail={error} /></div>}

      <form className="stack" onSubmit={submit} noValidate>
        <section className="card">
          <div className="card-head"><h2 className="t-section">Now</h2></div>
          <div className="fact-grid">
            <Fact label="Plan">{record.plan_code ? planLabel(record.plan_code) : "Not recorded"}</Fact>
            {record.plan_option && <Fact label="Option">{optionLabel(record.plan_code, record.plan_option)}</Fact>}
            <Fact label="Premium">{record.premium_cents !== null
              ? `${formatMoney(record.premium_cents, record.currency)} ${PER[currentFrequency]}` : "Not recorded"}</Fact>
            <Fact label="Cover">{record.cover_cents !== null
              ? formatMoney(record.cover_cents, record.currency) : "Not recorded"}</Fact>
          </div>
        </section>

        <section className="card">
          <div className="card-head"><h2 className="t-section">New plan</h2></div>
          <div className="form-grid">
            <Select label="Plan" value={plan.plan_code} onChange={choosePlan}
              options={PLANS} error={errors.plan_code} disabled={!live} />
            {planOptions.length > 1 && (
              <Select label="Plan option" value={plan.plan_option}
                onChange={(value) => setPlan((p) => ({ ...p, plan_option: value }))}
                options={[{ value: "", label: "Choose" }, ...planOptions]}
                hint="Priced by the main member's age today" error={errors.plan_option}
                disabled={!live} />
            )}
            <Select label="Payment frequency" value={onceOff ? "once_off" : plan.frequency}
              onChange={(value) => setPlan((p) => ({ ...p, frequency: value as Frequency }))}
              options={onceOff ? ONCE_OFF : FREQUENCIES} disabled={onceOff || !live}
              hint={onceOff ? "This plan is paid once" : undefined} error={errors.frequency} />
            {!onceOff && (
              <Select label="Payment day" value={plan.payment_day}
                onChange={(value) => setPlan((p) => ({ ...p, payment_day: value }))}
                options={PAYMENT_DAYS} disabled={!live || (!!record.debit_day && currentFrequency !== "once_off")}
                hint={record.debit_day ? "Kept. Change it on Edit member." : "They have none yet"}
                error={errors.debit_day} />
            )}
            <div className="field">
              <span className="field-label">New premium</span>
              <div className="premium-readout" aria-live="polite">
                {"cents" in premium ? <>
                  <strong>{formatMoney(premium.cents)} {PER[onceOff ? "once_off" : plan.frequency]}</strong>
                  <span className="t-small muted">{premium.detail}</span>
                </> : <span className="t-small muted">{premium.problem}</span>}
              </div>
              <span className="field-hint">From the price list. It cannot be typed in.</span>
            </div>
            <div className="field">
              <span className="field-label">New cover</span>
              <div className="premium-readout" aria-live="polite">
                {"cents" in premium ? (premium.cover !== null
                  ? <strong>{formatMoney(premium.cover, premium.currency)}</strong>
                  : <span className="t-small muted">Not on the price list yet</span>)
                  : <span className="t-small muted">{premium.problem}</span>}
              </div>
              <span className="field-hint">From the price list.</span>
            </div>
          </div>
          {"cents" in premium && !unchanged && live && (
            <p className="t-small" style={{ marginBottom: 0 }}>
              From today, every unpaid premium still to come is replaced at{" "}
              <strong>{formatMoney(premium.cents)} {PER[onceOff ? "once_off" : plan.frequency]}</strong>.
              Premiums already paid, waived or overdue are not touched.
            </p>
          )}
          {unchanged && (
            <p className="t-small muted" style={{ marginBottom: 0 }}>
              This is the plan and price they are on now.
            </p>
          )}
        </section>

        <div className="page-foot">
          {back}
          <Button variant="primary" type="submit" loading={saving} loadingLabel="Changing…"
            disabled={!live || unchanged || !("cents" in premium)}>
            Change plan
          </Button>
        </div>
      </form>
    </div>
  );
}
