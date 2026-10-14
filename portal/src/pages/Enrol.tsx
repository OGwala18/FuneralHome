import { useEffect, useState, type FormEvent } from "react";
import {
  ApiError, enrolMember, fetchEnquiry, fetchNextPolicyNumber,
  type EnquiryDetail, type PaymentMethod,
} from "@/lib/api";
import { fullName, toCents } from "@/lib/derive";
import { navigate } from "@/lib/router";
import { PAYMENT_METHODS, today } from "@/components/PaymentForm";
import { Button, Field, Notice, Select, Skeleton } from "@/components/ui";

/**
 * Enrol a main member: who they are, how to reach them, their policy and how
 * it is paid. Started from an enquiry, everything the family already typed on
 * the website is filled in; started from Members, it is a blank walk-in form.
 *
 * Saving creates the person, the policy and a year of premium instalments in
 * one step, then opens the policy so the dependants can be added straight away.
 */

const LANGUAGES = [
  { value: "zu", label: "isiZulu" },
  { value: "en", label: "English" },
  { value: "xh", label: "isiXhosa" },
  { value: "af", label: "Afrikaans" },
  { value: "st", label: "Sesotho" },
  { value: "other", label: "Other" },
];

const PLANS = [
  { value: "", label: "Not chosen yet" },
  { value: "plan_a", label: "Plan A" },
  { value: "plan_b", label: "Plan B" },
  { value: "plan_c", label: "Plan C" },
  { value: "dome_plan", label: "Dome Plan" },
];

const GENDERS = [
  { value: "", label: "From the ID number" },
  { value: "female", label: "Female" },
  { value: "male", label: "Male" },
];

const DEBIT_DAYS = [
  { value: "", label: "No fixed day" },
  ...Array.from({ length: 31 }, (_, i) => ({ value: String(i + 1), label: String(i + 1) })),
];

const FREQUENCIES = [
  { value: "monthly", label: "Monthly" },
  { value: "once_off", label: "Once-off" },
];

const BLANK = {
  first_names: "", surname: "", initials: "", id_number: "", date_of_birth: "", gender: "",
  email: "", mobile: "", language_preference: "zu",
  address_line1: "", address_line2: "", suburb: "", city: "", province: "KwaZulu-Natal",
  postal_code: "",
  policy_number: "", plan_code: "", entry_date: today(), premium: "", cover: "",
  payment_method: "undecided", debit_day: "", frequency: "monthly",
};

type Form = typeof BLANK;

const PAYMENT_PREFERENCES = new Set(["debit_order", "eft", "cash", "card", "undecided"]);

/** What the family already told us on the website, mapped onto the form. */
const fromEnquiry = (e: EnquiryDetail, form: Form): Form => ({
  ...form,
  first_names: e.first_name,
  surname: e.surname,
  id_number: e.id_number ?? "",
  date_of_birth: e.date_of_birth ?? "",
  email: e.email ?? "",
  mobile: e.mobile_number,
  language_preference: e.language_preference,
  address_line1: e.address_line1 ?? "",
  address_line2: e.address_line2 ?? "",
  suburb: e.suburb_or_town ?? "",
  city: e.city ?? "",
  province: e.province ?? form.province,
  postal_code: e.postal_code ?? "",
  plan_code: e.plan_selected ?? (e.plan_interest !== "unsure" ? e.plan_interest : ""),
  premium: e.premium_amount_cents !== null ? (e.premium_amount_cents / 100).toFixed(2) : "",
  payment_method: e.payment_preference && PAYMENT_PREFERENCES.has(e.payment_preference)
    ? e.payment_preference : form.payment_method,
  frequency: e.payment_frequency ?? form.frequency,
});

const orNull = (value: string) => (value.trim() ? value.trim() : null);

export default function Enrol({ enquiryId }: { enquiryId?: string }) {
  const [form, setForm] = useState<Form>(BLANK);
  const [enquiry, setEnquiry] = useState<EnquiryDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      fetchNextPolicyNumber(),
      enquiryId ? fetchEnquiry(enquiryId) : Promise.resolve(null),
    ])
      .then(([next, found]) => {
        if (cancelled) return;
        setEnquiry(found);
        setForm((current) => {
          const base = { ...current, policy_number: next.policy_number };
          return found ? fromEnquiry(found, base) : base;
        });
      })
      .catch((err) => {
        if (!cancelled) setLoadError(err instanceof ApiError ? err.message : "Could not load this form.");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [enquiryId]);

  const set = (key: keyof Form) => (value: string) => setForm((f) => ({ ...f, [key]: value }));
  const err = (key: string) => errors[key];

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);

    const premium = toCents(form.premium);
    const cover = form.cover.trim() ? toCents(form.cover) : null;
    const local: Record<string, string> = {};
    if (premium === null) local.premium_cents = "Enter the monthly premium in rand, e.g. 250.00";
    if (form.cover.trim() && cover === null) local.cover_cents = "Enter the cover in rand, e.g. 10000";
    if (Object.keys(local).length) {
      setErrors(local);
      setError("Please check the highlighted fields.");
      return;
    }

    setErrors({});
    setSaving(true);
    try {
      const result = await enrolMember({
        enquiry_id: enquiryId ?? null,
        first_names: form.first_names.trim(),
        surname: form.surname.trim(),
        initials: orNull(form.initials),
        id_number: orNull(form.id_number),
        date_of_birth: orNull(form.date_of_birth),
        gender: (orNull(form.gender) as "male" | "female" | null),
        email: orNull(form.email),
        mobile: orNull(form.mobile),
        language_preference: form.language_preference,
        address_line1: orNull(form.address_line1),
        address_line2: orNull(form.address_line2),
        suburb: orNull(form.suburb),
        city: orNull(form.city),
        province: orNull(form.province),
        postal_code: orNull(form.postal_code),
        policy_number: form.policy_number.trim(),
        plan_code: orNull(form.plan_code),
        entry_date: orNull(form.entry_date),
        premium_cents: premium!,
        cover_cents: cover,
        payment_method: form.payment_method as PaymentMethod,
        debit_day: form.debit_day ? Number(form.debit_day) : null,
        frequency: form.frequency as "monthly" | "once_off",
      });
      navigate({ name: "policy", id: result.policy_id, addLives: true });
    } catch (e) {
      if (e instanceof ApiError) {
        setErrors(e.fieldErrors);
        setError(e.message);
      } else {
        setError("Could not save. Try again.");
      }
      window.scrollTo({ top: 0, behavior: "smooth" });
    } finally {
      setSaving(false);
    }
  };

  const back = enquiryId
    ? <Button variant="ghost" onClick={() => navigate({ name: "person", id: enquiryId })}>Back to enquiry</Button>
    : <Button variant="ghost" onClick={() => navigate({ name: "members" })}>Back to members</Button>;

  if (loading) {
    return <div className="page"><div className="page-head">{back}</div>
      <div className="card"><Skeleton rows={10} /></div></div>;
  }
  if (loadError) {
    return <div className="page"><div className="page-head">{back}</div>
      <Notice tone="error" title="Could not open the enrolment form." detail={loadError} /></div>;
  }
  if (enquiry?.person_id) {
    return <div className="page"><div className="page-head">{back}</div>
      <Notice tone="success" title={`${fullName(enquiry)} is already a member.`}
        detail="This enquiry was enrolled before. Open their record to see the policy."
        action={<Button small variant="primary"
          onClick={() => navigate({ name: "member", id: enquiry.person_id! })}>View member</Button>} />
    </div>;
  }

  return (
    <div className="page">
      <div className="row" style={{ marginBottom: "var(--s16)" }}>{back}</div>
      <div className="page-head">
        <div className="page-head-text">
          <h1 className="t-heading">
            {enquiry ? `Enrol ${fullName(enquiry)}` : "Enrol a new member"}
          </h1>
          <p className="muted">
            {enquiry
              ? <>From enquiry <span className="ref">{enquiry.reference}</span>. Check what they typed against the paper application.</>
              : "For a walk-in or a paper application. Dependants are added on the next page."}
          </p>
        </div>
      </div>

      {error && <div style={{ marginBottom: "var(--s16)" }}>
        <Notice tone="error" title="Not saved yet." detail={error} /></div>}

      <form className="stack" onSubmit={submit} noValidate>
        <section className="card">
          <div className="card-head"><h2 className="t-section">The main member</h2></div>
          <div className="form-grid">
            <Field label="First names" value={form.first_names} onChange={set("first_names")}
              required error={err("first_names")} autoComplete="off" />
            <Field label="Surname" value={form.surname} onChange={set("surname")}
              required error={err("surname")} autoComplete="off" />
            <Field label="Initials" value={form.initials} onChange={set("initials")}
              hint="Optional" error={err("initials")} autoComplete="off" />
            <Field label="ID number" value={form.id_number} onChange={set("id_number")}
              hint="13 digits. Date of birth and gender are read from it."
              error={err("id_number")} autoComplete="off" />
            <Field label="Date of birth" type="date" value={form.date_of_birth}
              onChange={set("date_of_birth")} hint="Only needed without an ID number"
              error={err("date_of_birth")} />
            <Select label="Gender" value={form.gender} onChange={set("gender")}
              options={GENDERS} error={err("gender")} />
            <Select label="Language" value={form.language_preference}
              onChange={set("language_preference")} options={LANGUAGES} />
          </div>
        </section>

        <section className="card">
          <div className="card-head"><h2 className="t-section">How to reach them</h2></div>
          <div className="form-grid">
            <Field label="Mobile" type="tel" value={form.mobile} onChange={set("mobile")}
              hint="Used for WhatsApp payment reminders" error={err("mobile")} autoComplete="off" />
            <Field label="Email" type="email" value={form.email} onChange={set("email")}
              hint="Optional" error={err("email")} autoComplete="off" />
          </div>
          <div className="form-grid" style={{ marginTop: "var(--s8)" }}>
            <Field label="Street address" value={form.address_line1} onChange={set("address_line1")}
              error={err("address_line1")} autoComplete="off" />
            <Field label="Address line 2" value={form.address_line2} onChange={set("address_line2")}
              hint="Optional" error={err("address_line2")} autoComplete="off" />
            <Field label="Suburb or area" value={form.suburb} onChange={set("suburb")}
              error={err("suburb")} autoComplete="off" />
            <Field label="City or town" value={form.city} onChange={set("city")}
              error={err("city")} autoComplete="off" />
            <Field label="Province" value={form.province} onChange={set("province")}
              error={err("province")} autoComplete="off" />
            <Field label="Postal code" value={form.postal_code} onChange={set("postal_code")}
              error={err("postal_code")} autoComplete="off" />
          </div>
        </section>

        <section className="card">
          <div className="card-head"><h2 className="t-section">The policy</h2></div>
          <div className="form-grid">
            <Field label="Policy number" value={form.policy_number} onChange={set("policy_number")}
              required hint="The next free number. Change it to match the paper file."
              error={err("policy_number")} autoComplete="off" />
            <Select label="Plan" value={form.plan_code} onChange={set("plan_code")}
              options={PLANS} error={err("plan_code")} />
            <Field label="Start date" type="date" value={form.entry_date} onChange={set("entry_date")}
              error={err("entry_date")} />
            <Field label="Premium (R)" value={form.premium} onChange={set("premium")} required
              hint="What the family pays each time, e.g. 250.00" error={err("premium_cents")}
              autoComplete="off" />
            <Field label="Cover (R)" value={form.cover} onChange={set("cover")}
              hint="Optional, e.g. 10000" error={err("cover_cents")} autoComplete="off" />
          </div>
        </section>

        <section className="card">
          <div className="card-head"><h2 className="t-section">How it is paid</h2></div>
          <p className="t-small muted" style={{ marginTop: 0 }}>
            No bank or card details are recorded here. Collection is arranged with the payment provider.
          </p>
          <div className="form-grid">
            <Select label="Method" value={form.payment_method} onChange={set("payment_method")}
              options={PAYMENT_METHODS} error={err("payment_method")} />
            <Select label="Debit day" value={form.debit_day} onChange={set("debit_day")}
              options={DEBIT_DAYS} hint="The day of the month it falls due" error={err("debit_day")} />
            <Select label="Frequency" value={form.frequency} onChange={set("frequency")}
              options={FREQUENCIES} error={err("frequency")} />
          </div>
        </section>

        <div className="page-foot">
          {back}
          <Button variant="primary" type="submit" loading={saving} loadingLabel="Enrolling…">
            Enrol and add dependants
          </Button>
        </div>
      </form>
    </div>
  );
}
