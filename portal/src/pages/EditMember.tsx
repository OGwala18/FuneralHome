import { useEffect, useState, type FormEvent } from "react";
import {
  ApiError, fetchMemberForEdit, fetchPlanPrices, updateMember,
  type Frequency, type MemberEdit, type PayBranch, type PaymentMethod, type PlanPrice,
} from "@/lib/api";
import { SOUTH_AFRICA, WORKING } from "@/lib/compliance";
import { decodeSaId } from "@/lib/derive";
import { navigate } from "@/lib/router";
import MemberFormSections, {
  BLANK, IN_PERSON, orNull, type MemberFormValues,
} from "@/components/MemberForm";
import ChangeHistory from "@/components/ChangeHistory";
import { Badge, Button, Notice, Skeleton } from "@/components/ui";

/**
 * Correct a member after enrolment. The same form as enrolling them, filled
 * in with what is recorded, with the parts that identify the policy greyed
 * out: its number, the member's id, the plan, the start date, the frequency.
 * Staff fix their own capture mistakes here (an ID number, a surname, a
 * mobile, an address, the FICA answers, how the family pays).
 *
 * Every value a save overwrites is kept in the history below the form, with
 * who changed it and when, so a correction that was itself a mistake can be
 * put back from the record.
 */

/** "+27821234567" as "082 123 4567", the way staff type it. */
const localMobile = (e164: string | null) => {
  const match = /^\+27(\d{2})(\d{3})(\d{4})$/.exec(e164 ?? "");
  return match ? `0${match[1]} ${match[2]} ${match[3]}` : e164 ?? "";
};

const toForm = (m: MemberEdit): MemberFormValues => ({
  ...BLANK,
  first_names: m.first_names,
  surname: m.surname,
  initials: m.initials ?? "",
  id_number: m.id_number ?? "",
  date_of_birth: m.date_of_birth ?? "",
  gender: m.gender === "male" || m.gender === "female" ? m.gender : "",
  email: m.email ?? "",
  mobile: localMobile(m.mobile),
  language_preference: m.language_preference,
  address_line1: m.address_line1 ?? "",
  address_line2: m.address_line2 ?? "",
  suburb: m.suburb ?? "",
  city: m.city ?? "",
  province: m.province ?? "",
  postal_code: m.postal_code ?? "",
  country_of_birth: m.country_of_birth ?? "",
  citizenship: m.citizenship ?? "",
  passport_number: m.passport_number ?? "",
  employment_status: m.employment_status ?? "",
  employer_name: m.employer_name ?? "",
  industry: m.industry ?? "",
  occupation: m.occupation ?? "",
  job_role: m.job_role ?? "",
  source_of_funds: m.source_of_funds ?? "",
  source_of_funds_other: m.source_of_funds_other ?? "",
  salary_day: m.salary_day ? String(m.salary_day) : "",
  policy_number: m.policy_number,
  plan_code: m.plan_code ?? "",
  plan_option: m.plan_option ?? "",
  entry_date: m.entry_date ?? "",
  frequency: (m.frequency ?? "monthly") as Frequency,
  payment_day: m.debit_day ? String(m.debit_day) : "",
  payment_method: m.payment_method ?? "undecided",
  pay_branch_code: m.pay_branch_code ?? "",
  notes: m.notes ?? "",
});

export default function EditMember({ policyId }: { policyId: string }) {
  const [record, setRecord] = useState<MemberEdit | null>(null);
  const [form, setForm] = useState<MemberFormValues>(BLANK);
  const [prices, setPrices] = useState<PlanPrice[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState(false);
  // Bumped after a save, so the history below shows the change at once.
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([fetchMemberForEdit(policyId), fetchPlanPrices()])
      .then(([found, priceList]) => {
        if (cancelled) return;
        setRecord(found);
        setPrices(priceList);
        setForm(toForm(found));
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof ApiError ? err.message : "Could not load this member.");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [policyId]);

  const decoded = decodeSaId(form.id_number);
  const working = WORKING.has(form.employment_status);
  const southAfrican = form.citizenship === SOUTH_AFRICA;
  const onceOff = form.frequency === "once_off";

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSaved(false);

    const local: Record<string, string> = {};
    if (!onceOff && !form.payment_day) local.debit_day = "Choose the payment day";
    if (IN_PERSON.has(form.payment_method) && !form.pay_branch_code) {
      local.pay_branch_code = "Choose the branch they will pay at";
    }
    if (Object.keys(local).length) {
      setErrors(local);
      setError("Please check the highlighted fields.");
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }

    setErrors({});
    setSaving(true);
    try {
      const result = await updateMember(policyId, {
        first_names: form.first_names.trim(),
        surname: form.surname.trim(),
        initials: orNull(form.initials),
        id_number: orNull(form.id_number),
        // With a valid ID the API reads both from it.
        date_of_birth: decoded ? null : orNull(form.date_of_birth),
        gender: decoded ? null : (orNull(form.gender) as "male" | "female" | null),
        email: orNull(form.email),
        mobile: orNull(form.mobile),
        language_preference: form.language_preference,
        address_line1: orNull(form.address_line1),
        address_line2: orNull(form.address_line2),
        suburb: orNull(form.suburb),
        city: orNull(form.city),
        province: orNull(form.province),
        postal_code: orNull(form.postal_code),
        country_of_birth: orNull(form.country_of_birth),
        citizenship: orNull(form.citizenship),
        passport_number: southAfrican ? null : orNull(form.passport_number),
        employment_status: orNull(form.employment_status),
        employer_name: working ? orNull(form.employer_name) : null,
        industry: working ? orNull(form.industry) : null,
        occupation: working ? orNull(form.occupation) : null,
        job_role: working ? orNull(form.job_role) : null,
        source_of_funds: orNull(form.source_of_funds),
        source_of_funds_other: form.source_of_funds === "other"
          ? orNull(form.source_of_funds_other) : null,
        salary_day: form.salary_day ? Number(form.salary_day) : null,
        payment_method: form.payment_method as PaymentMethod,
        pay_branch_code: IN_PERSON.has(form.payment_method)
          ? (form.pay_branch_code as PayBranch) : null,
        debit_day: !onceOff && form.payment_day ? Number(form.payment_day) : null,
        notes: orNull(form.notes),
      });
      setRecord(result);
      setForm(toForm(result));
      setSaved(true);
      setVersion((v) => v + 1);
    } catch (e) {
      if (e instanceof ApiError) {
        setErrors(e.fieldErrors);
        setError(e.message);
      } else {
        setError("Could not save. Try again.");
      }
    } finally {
      setSaving(false);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  };

  const back = <Button variant="ghost" onClick={() => navigate({ name: "policy", id: policyId })}>
    Back to policy</Button>;

  if (loading) {
    return <div className="page"><div className="page-head">{back}</div>
      <div className="card"><Skeleton rows={10} /></div></div>;
  }
  if (loadError || !record) {
    return <div className="page"><div className="page-head">{back}</div>
      <Notice tone="error" title="Could not open this member." detail={loadError ?? "It may have been removed."} /></div>;
  }

  const optionLabel = prices.find((p) => p.plan_code === record.plan_code
    && p.option_code === record.plan_option)?.option_label ?? record.plan_option;

  return (
    <div className="page">
      <div className="row" style={{ marginBottom: "var(--s16)" }}>
        {back}
        <Badge tone={record.status_code === "active" ? "success" : "neutral"}>{record.status_label}</Badge>
      </div>
      <div className="page-head">
        <div className="page-head-text">
          <h1 className="t-heading">Edit {record.first_names} {record.surname}</h1>
          <p className="muted">
            Policy <span className="ref">{record.policy_number}</span>. Correct what was
            captured wrongly. Greyed-out fields identify the policy and are not changed here;
            every value you overwrite is kept in the history at the bottom.
          </p>
        </div>
      </div>

      {saved && <div style={{ marginBottom: "var(--s16)" }}>
        <Notice tone="success" title="Saved."
          detail="The old values are in the change history below." /></div>}
      {error && <div style={{ marginBottom: "var(--s16)" }}>
        <Notice tone="error" title="Not saved yet." detail={error} /></div>}

      <form className="stack" onSubmit={submit} noValidate>
        <MemberFormSections mode="edit" form={form} setForm={setForm} errors={errors}
          prices={prices}
          recorded={{
            personId: record.person_id, premiumCents: record.premium_cents,
            coverCents: record.cover_cents, currency: record.currency, optionLabel,
          }}
          onChangePlan={() => navigate({ name: "changePlan", id: policyId })}
          onOpenPolicy={() => navigate({ name: "policy", id: policyId })} />

        <div className="page-foot">
          {back}
          <Button variant="primary" type="submit" loading={saving} loadingLabel="Saving…">
            Save changes
          </Button>
        </div>
      </form>

      <div style={{ marginTop: "var(--s24)" }}>
        <ChangeHistory policyId={policyId} version={version} />
      </div>
    </div>
  );
}
