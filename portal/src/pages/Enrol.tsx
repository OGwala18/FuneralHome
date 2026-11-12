import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  ApiError, PAY_BRANCHES, enrolMember, fetchEnquiry, fetchNextPolicyNumber, fetchPlanPrices,
  type EnquiryDetail, type Frequency, type PayBranch, type PaymentMethod, type PlanPrice,
} from "@/lib/api";
import {
  COUNTRIES, EMPLOYMENT_STATUSES, INDUSTRIES, JOB_ROLES, SALARY_DAYS, SOURCES_OF_FUNDS,
  SOUTH_AFRICA, WORKING, dayLabel,
} from "@/lib/compliance";
import { ageOn, decodeSaId, formatMoney, fullName } from "@/lib/derive";
import { navigate } from "@/lib/router";
import { PAYMENT_METHODS, today } from "@/components/PaymentForm";
import { Button, Field, Notice, Select, Skeleton } from "@/components/ui";

/**
 * Enrol a main member: who they are, the compliance questions, how to reach
 * them, their policy, who it pays out to, and how it is paid. Started from an
 * enquiry, everything the family already typed on the website is filled in;
 * started from Members, it is a blank walk-in form.
 *
 * The premium is not typed in. It is read from the price list for the plan,
 * the option and the member's age, and the API prices the policy again from
 * the same list when it is saved.
 *
 * Saving creates the person, the policy, the beneficiary and the premium
 * schedule in one step, then opens the policy so the dependants can be added
 * straight away.
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
  { value: "", label: "Choose a plan" },
  { value: "plan_a", label: "Plan A (Urban)" },
  { value: "plan_b", label: "Plan B (Emakhaya)" },
  { value: "plan_c", label: "Plan C (Singles/Couples)" },
  { value: "dome_plan", label: "Dome Plan" },
];

const GENDERS = [
  { value: "", label: "Choose" },
  { value: "female", label: "Female" },
  { value: "male", label: "Male" },
];

const FREQUENCIES: { value: Frequency; label: string }[] = [
  { value: "monthly", label: "Monthly" },
  { value: "quarterly", label: "Quarterly" },
  { value: "annually", label: "Annually" },
];
const ONCE_OFF = [{ value: "once_off", label: "Once-off" }];

const PER: Record<Frequency, string> = {
  monthly: "a month", quarterly: "a quarter", annually: "a year", once_off: "once-off",
};
const MONTHS: Record<Frequency, number> = { monthly: 1, quarterly: 3, annually: 12, once_off: 1 };

// The payment day, for every method (the API accepts only these). The owner,
// 11 Nov 2026: the 1st, the 25th or the LAST DAY of the month (31, which the
// schedule puts on the 28th, 29th, 30th or 31st). WhatsApp reminds the family on
// that day, and once more the day after if it is still unpaid.
const PAYMENT_DAYS = [
  { value: "", label: "Choose a day" },
  ...[1, 25, 31].map((day) => ({ value: String(day), label: dayLabel(day) })),
];

// Paying in person: which of the three branches.
const IN_PERSON = new Set(["cash", "card"]);
const BRANCH_OPTIONS = [{ value: "", label: "Choose a branch" }, ...PAY_BRANCHES];

// Debit orders are built but not switched on. The option is shown so staff and
// the owner can see where it goes, and cannot be chosen.
const METHODS = PAYMENT_METHODS.map((m) => m.value === "debit_order"
  ? { ...m, label: "Debit order (coming soon)", disabled: true }
  : m.value === "cash" ? { ...m, label: "Cash at a branch" }
  : m.value === "card" ? { ...m, label: "Card, in person at a branch" } : m);

const BLANK = {
  first_names: "", surname: "", initials: "", id_number: "", date_of_birth: "", gender: "",
  email: "", mobile: "", language_preference: "zu",
  address_line1: "", address_line2: "", suburb: "", city: "", province: "KwaZulu-Natal",
  postal_code: "",
  country_of_birth: SOUTH_AFRICA, citizenship: SOUTH_AFRICA, passport_number: "",
  employment_status: "", employer_name: "", industry: "", occupation: "", job_role: "",
  source_of_funds: "", source_of_funds_other: "", salary_day: "",
  policy_number: "", plan_code: "", plan_option: "", entry_date: today(),
  frequency: "monthly" as Frequency,
  payment_day: "",
  payment_method: "undecided",
  pay_branch_code: "",
  // "later": one of the dependants, chosen on the next page once they're added.
  // "someone": a person not covered by the policy, with full details.
  ben_mode: "later" as "later" | "someone",
  ben_first_names: "", ben_surname: "", ben_id_number: "", ben_date_of_birth: "",
  ben_relationship: "", ben_mobile: "", ben_email: "",
  ben_address_line1: "", ben_suburb: "", ben_city: "", ben_postal_code: "",
  notes: "",
};

type Form = typeof BLANK;

// Debit order is not offered yet, so a family who asked for one on the website
// starts as "not decided" and staff agree another method with them.
const PAYMENT_PREFERENCES = new Set(["eft", "cash", "card", "undecided"]);

/** "Nandi Mkhize" as first names and surname. The surname is the last word. */
const splitName = (name: string | null) => {
  const words = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (words.length < 2) return { first: words[0] ?? "", last: "" };
  return { first: words.slice(0, -1).join(" "), last: words[words.length - 1] };
};

const WEBSITE_LABELS: Record<string, string> = {
  single: "Single", married: "Married", customary_union: "Customary union",
  divorced: "Divorced", widowed: "Widowed", other: "Other",
  edolobheni: "Edolobheni (urban)", emakhaya: "Emakhaya (rural)",
  flat_lid: "Flat lid", casket: "Casket",
  morning: "Morning (8am–12pm)", afternoon: "Afternoon (12pm–5pm)", evening: "Evening (5pm–8pm)",
};

/** "customary_union" as "Customary union", unless there is a better label. */
const websiteLabel = (value: string) => WEBSITE_LABELS[value]
  ?? (value.charAt(0).toUpperCase() + value.slice(1)).replace(/_/g, " ");

/**
 * Everything the website asked that has no field of its own on this form,
 * as lines for the policy's notes. Nothing the family typed is dropped: what
 * has a field is filled in above, and the rest lands here.
 */
const websiteNotes = (e: EnquiryDetail): string => {
  const lines: string[] = [];
  const add = (label: string, value: string | number | null | undefined) => {
    if (value !== null && value !== undefined && String(value).trim()) {
      lines.push(`${label}: ${String(value).trim()}`);
    }
  };
  add("Marital status", e.marital_status && websiteLabel(e.marital_status));
  if (e.next_of_kin_name || e.next_of_kin_mobile) {
    add("Next of kin", [
      e.next_of_kin_name,
      e.next_of_kin_relationship && `(${e.next_of_kin_relationship})`,
      e.next_of_kin_mobile,
    ].filter(Boolean).join(" "));
  }
  add("Dependants listed", e.number_of_dependants);
  add("Cover area", e.cover_area && websiteLabel(e.cover_area));
  add("Coffin", e.coffin_choice && websiteLabel(e.coffin_choice));
  add("Age band", e.age_band);
  if (e.payment_preference === "debit_order") {
    lines.push("Asked to pay by debit order (not available yet)");
  }
  add("Best time to call", e.best_contact_time && websiteLabel(e.best_contact_time));
  add("Heard about us", e.how_heard && websiteLabel(e.how_heard));
  add("Their note", e.notes);
  return lines.length ? [`From website enquiry ${e.reference}:`, ...lines].join("\n") : "";
};

/** What the family already told us on the website, mapped onto the form. */
const fromEnquiry = (e: EnquiryDetail, form: Form, prices: PlanPrice[]): Form => {
  const beneficiary = splitName(e.beneficiary_name);
  const plan = e.plan_selected ?? (e.plan_interest !== "unsure" ? e.plan_interest : "");
  // From the price list, as choosing the plan by hand does: the Dome Plan has
  // been monthly since the flyer prices (0024), so it is never assumed once-off.
  const onceOff = prices.some((p) => p.plan_code === plan && p.billing === "once_off");
  return {
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
    plan_code: plan,
    frequency: onceOff ? "once_off" : form.frequency === "once_off" ? "monthly" : form.frequency,
    payment_method: e.payment_preference && PAYMENT_PREFERENCES.has(e.payment_preference)
      ? e.payment_preference : form.payment_method,
    // The website asked who the beneficiary is. Start with that person; staff
    // switch to a dependant if it turns out to be one of the family.
    ben_mode: beneficiary.first ? "someone" : form.ben_mode,
    ben_first_names: beneficiary.first,
    ben_surname: beneficiary.last,
    ben_relationship: e.beneficiary_relationship ?? "",
    ben_mobile: e.beneficiary_mobile ?? "",
    notes: websiteNotes(e),
  };
};

const orNull = (value: string) => (value.trim() ? value.trim() : null);

type Quote =
  | { cents: number; detail: string; cover: number | null; currency: string }
  | { problem: string };

/**
 * The premium for the chosen plan, option, age and frequency, read from the
 * price list exactly as the API does (enrolment.price). Shown, never typed.
 */
const quote = (prices: PlanPrice[], form: Form, dob: string): Quote => {
  const rows = prices.filter((p) => p.plan_code === form.plan_code);
  if (!form.plan_code) return { problem: "Choose a plan to see the premium." };
  if (!rows.length) return { problem: "This plan has no price on record yet." };

  const options = [...new Set(rows.map((r) => r.option_code))];
  const option = options.length === 1 ? options[0] : form.plan_option;
  if (!option) return { problem: "Choose the plan option to see the premium." };

  const bands = rows.filter((r) => r.option_code === option);
  let match: PlanPrice | undefined = bands[0];
  if (bands.some((r) => r.min_age !== null || r.max_age !== null)) {
    const age = dob ? ageOn(dob, form.entry_date || today()) : null;
    if (age === null) return { problem: "Priced by age. Enter the ID number or date of birth." };
    match = bands.find((r) => (r.min_age === null || age >= r.min_age)
      && (r.max_age === null || age <= r.max_age));
    if (!match) {
      const low = Math.min(...bands.map((r) => r.min_age ?? 0));
      const high = Math.max(...bands.map((r) => r.max_age ?? 0));
      return { problem: `${bands[0].option_label} is for ages ${low} to ${high}. This member is ${age}.` };
    }
  }

  const cover = match.cover_cents;
  const currency = match.currency;
  if (match.billing === "once_off") {
    return { cents: match.premium_cents, detail: "Paid once", cover, currency };
  }
  const months = MONTHS[form.frequency];
  return {
    cover,
    currency,
    cents: match.premium_cents * months,
    detail: months === 1
      ? match.option_label
      : `${months} × ${formatMoney(match.premium_cents, match.currency)} a month`,
  };
};

export default function Enrol({ enquiryId }: { enquiryId?: string }) {
  const [form, setForm] = useState<Form>(BLANK);
  const [enquiry, setEnquiry] = useState<EnquiryDetail | null>(null);
  const [prices, setPrices] = useState<PlanPrice[]>([]);
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
      fetchPlanPrices(),
      enquiryId ? fetchEnquiry(enquiryId) : Promise.resolve(null),
    ])
      .then(([next, priceList, found]) => {
        if (cancelled) return;
        setEnquiry(found);
        setPrices(priceList);
        setForm((current) => {
          const base = { ...current, policy_number: next.policy_number };
          return found ? fromEnquiry(found, base, priceList) : base;
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

  // A valid SA ID number fills in the date of birth and gender; they are shown,
  // not typed. Without one (a passport holder) they are entered by hand.
  const decoded = decodeSaId(form.id_number);
  const dob = decoded?.dob ?? form.date_of_birth;
  const benDecoded = decodeSaId(form.ben_id_number);
  const benDob = benDecoded?.dob ?? form.ben_date_of_birth;

  const planOptions = useMemo(() => {
    const seen = new Map<string, string>();
    prices.filter((p) => p.plan_code === form.plan_code)
      .forEach((p) => seen.set(p.option_code, p.option_label));
    return [...seen].map(([value, label]) => ({ value, label }));
  }, [prices, form.plan_code]);
  const onceOff = prices.some((p) => p.plan_code === form.plan_code && p.billing === "once_off");
  const premium = quote(prices, form, dob);

  const choosePlan = (plan: string) => setForm((f) => {
    const isOnceOff = prices.some((p) => p.plan_code === plan && p.billing === "once_off");
    return {
      ...f,
      plan_code: plan,
      plan_option: "",
      frequency: isOnceOff ? "once_off" : f.frequency === "once_off" ? "monthly" : f.frequency,
    };
  });

  const working = WORKING.has(form.employment_status);
  const southAfrican = form.citizenship === SOUTH_AFRICA;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);

    const local: Record<string, string> = {};
    if (!form.plan_code) local.plan_code = "Choose a plan";
    if (form.frequency !== "once_off" && !form.payment_day) {
      local.debit_day = "Choose the payment day";
    }
    if (form.payment_method === "debit_order") {
      local.payment_method = "Debit orders are not switched on yet. Choose another method";
    }
    if (IN_PERSON.has(form.payment_method) && !form.pay_branch_code) {
      local.pay_branch_code = "Choose the branch they will pay at";
    }
    if (form.ben_mode === "someone" && !benDob) {
      local["beneficiary.date_of_birth"] = "Enter the date of birth, or a valid ID number";
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
      const result = await enrolMember({
        enquiry_id: enquiryId ?? null,
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
        country_of_birth: form.country_of_birth,
        citizenship: form.citizenship,
        passport_number: southAfrican ? null : orNull(form.passport_number),
        employment_status: form.employment_status,
        employer_name: working ? orNull(form.employer_name) : null,
        industry: working ? orNull(form.industry) : null,
        occupation: working ? orNull(form.occupation) : null,
        job_role: working ? orNull(form.job_role) : null,
        source_of_funds: form.source_of_funds,
        source_of_funds_other: form.source_of_funds === "other"
          ? orNull(form.source_of_funds_other) : null,
        salary_day: form.salary_day ? Number(form.salary_day) : null,
        policy_number: form.policy_number.trim(),
        plan_code: form.plan_code,
        plan_option: orNull(form.plan_option),
        entry_date: orNull(form.entry_date),
        payment_method: form.payment_method as PaymentMethod,
        // The payment day, whatever the method. None for a once-off plan.
        debit_day: form.frequency !== "once_off" && form.payment_day
          ? Number(form.payment_day) : null,
        frequency: form.frequency,
        pay_branch_code: IN_PERSON.has(form.payment_method)
          ? (form.pay_branch_code as PayBranch) : null,
        notes: orNull(form.notes),
        beneficiary: form.ben_mode === "later" ? null : {
          first_names: form.ben_first_names.trim(),
          surname: form.ben_surname.trim(),
          id_number: orNull(form.ben_id_number),
          date_of_birth: benDecoded ? null : orNull(form.ben_date_of_birth),
          relationship: orNull(form.ben_relationship),
          mobile: orNull(form.ben_mobile),
          email: orNull(form.ben_email),
          address_line1: orNull(form.ben_address_line1),
          suburb: orNull(form.ben_suburb),
          city: orNull(form.ben_city),
          postal_code: orNull(form.ben_postal_code),
        },
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
              : "Follows the paper application form, section by section. Spouse, children and extended family (sections 4–7 on paper) are added on the next page."}
          </p>
        </div>
      </div>

      {error && <div style={{ marginBottom: "var(--s16)" }}>
        <Notice tone="error" title="Not saved yet." detail={error} /></div>}

      <form className="stack" onSubmit={submit} noValidate>
        <section className="card">
          <div className="card-head"><h2 className="t-section">1. Plan</h2></div>
          <div className="form-grid">
            <Field label="Policy number" value={form.policy_number} onChange={set("policy_number")}
              required hint="The next free IFH number. Change it to match the paper file."
              error={err("policy_number")} autoComplete="off" />
            <Select label="Plan" value={form.plan_code} onChange={choosePlan}
              options={PLANS} error={err("plan_code")} />
            {planOptions.length > 1 && (
              <Select label="Plan option" value={form.plan_option} onChange={set("plan_option")}
                options={[{ value: "", label: "Choose" }, ...planOptions]}
                hint={enquiry?.coffin_choice && form.plan_code === "plan_c"
                  ? `Website: ${websiteLabel(enquiry.coffin_choice).toLowerCase()}${enquiry.age_band ? `, ages ${enquiry.age_band}` : ""}`
                  : "Priced by the main member's age"}
                error={err("plan_option")} />
            )}
            <Field label="Start date" type="date" value={form.entry_date} onChange={set("entry_date")}
              error={err("entry_date")} />
          </div>
        </section>

        <section className="card">
          <div className="card-head"><h2 className="t-section">2. Main member</h2></div>
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
            <Field label="Date of birth" type="date" value={dob}
              onChange={set("date_of_birth")} disabled={!!decoded}
              hint={decoded ? "Read from the ID number" : "Needed when there is no SA ID number"}
              error={err("date_of_birth")} />
            <Select label="Gender" value={decoded?.gender ?? form.gender} onChange={set("gender")}
              options={GENDERS} disabled={!!decoded}
              hint={decoded ? "Read from the ID number" : undefined} error={err("gender")} />
            <Select label="Language" value={form.language_preference}
              onChange={set("language_preference")} options={LANGUAGES} />
          </div>
          <div className="form-grid" style={{ marginTop: "var(--s8)" }}>
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
          <div className="card-head"><h2 className="t-section">3. Citizenship and income (FICA)</h2></div>
          <div className="form-grid">
            <Select label="Country of birth" value={form.country_of_birth}
              onChange={set("country_of_birth")} options={COUNTRIES}
              error={err("country_of_birth")} />
            <Select label="Citizenship" value={form.citizenship}
              onChange={(value) => setForm((f) => ({
                ...f, citizenship: value,
                passport_number: value === SOUTH_AFRICA ? "" : f.passport_number,
              }))}
              options={COUNTRIES} error={err("citizenship")} />
            <Field label="Passport number" value={form.passport_number}
              onChange={set("passport_number")} disabled={southAfrican}
              hint={southAfrican ? "Only for members who are not South African"
                : "Needed if they have no SA ID number"}
              error={err("passport_number")} autoComplete="off" />
          </div>
          <div className="form-grid" style={{ marginTop: "var(--s8)" }}>
            <Select label="Employment status" value={form.employment_status}
              onChange={set("employment_status")}
              options={[{ value: "", label: "Choose" }, ...EMPLOYMENT_STATUSES]}
              error={err("employment_status")} />
            <Select label="Source of funds" value={form.source_of_funds}
              onChange={set("source_of_funds")}
              options={[{ value: "", label: "Choose" }, ...SOURCES_OF_FUNDS]}
              hint="Where the money for the premium comes from" error={err("source_of_funds")} />
            {form.source_of_funds === "other" && (
              <Field label="Other source of funds" value={form.source_of_funds_other}
                onChange={set("source_of_funds_other")} error={err("source_of_funds_other")}
                autoComplete="off" />
            )}
            <Select label="Salary day" value={form.salary_day} onChange={set("salary_day")}
              options={SALARY_DAYS} hint="The day of the month they are paid"
              error={err("salary_day")} />
          </div>
          {working && (
            <div className="form-grid" style={{ marginTop: "var(--s8)" }}>
              <Field label={form.employment_status === "self_employed" ? "Business name" : "Employer"}
                value={form.employer_name} onChange={set("employer_name")}
                error={err("employer_name")} autoComplete="off" />
              <Select label="Industry" value={form.industry} onChange={set("industry")}
                options={[{ value: "", label: "Choose" }, ...INDUSTRIES]} error={err("industry")} />
              <Field label="Profession" value={form.occupation} onChange={set("occupation")}
                hint="e.g. Nurse, Driver, Teacher" error={err("occupation")} autoComplete="off" />
              <Select label="Role" value={form.job_role} onChange={set("job_role")}
                options={[{ value: "", label: "Choose" }, ...JOB_ROLES]} error={err("job_role")} />
            </div>
          )}
        </section>


        <section className="card">
          <div className="card-head"><h2 className="t-section">4. Beneficiary</h2></div>
          <p className="t-small muted" style={{ marginTop: 0 }}>Who receives the payout.</p>
          <div className="choice-row" role="radiogroup" aria-label="Who is the beneficiary">
            <label className="choice">
              <input type="radio" name="ben_mode" checked={form.ben_mode === "later"}
                onChange={() => setForm((f) => ({ ...f, ben_mode: "later" }))} />
              One of the dependants
              <span className="t-small muted"> &middot; choose on the next page, once they&rsquo;re added</span>
            </label>
            <label className="choice">
              <input type="radio" name="ben_mode" checked={form.ben_mode === "someone"}
                onChange={() => setForm((f) => ({ ...f, ben_mode: "someone" }))} />
              Someone not on the policy
              <span className="t-small muted"> &middot; e.g. a brother with his own cover</span>
            </label>
          </div>
          {form.ben_mode === "someone" && (
            <div className="form-grid" style={{ marginTop: "var(--s16)" }}>
              <Field label="First names" value={form.ben_first_names} onChange={set("ben_first_names")}
                required error={err("beneficiary.first_names")} autoComplete="off" />
              <Field label="Surname" value={form.ben_surname} onChange={set("ben_surname")}
                required error={err("beneficiary.surname")} autoComplete="off" />
              <Field label="Relationship" value={form.ben_relationship}
                onChange={set("ben_relationship")} hint="To the main member, e.g. Brother"
                error={err("beneficiary.relationship")} autoComplete="off" />
              <Field label="ID number" value={form.ben_id_number} onChange={set("ben_id_number")}
                hint="Date of birth is read from it" error={err("beneficiary.id_number")}
                autoComplete="off" />
              <Field label="Date of birth" type="date" value={benDob}
                onChange={set("ben_date_of_birth")} disabled={!!benDecoded} required
                hint={benDecoded ? "Read from the ID number" : "Required"}
                error={err("beneficiary.date_of_birth")} />
              <Field label="Mobile" type="tel" value={form.ben_mobile} onChange={set("ben_mobile")}
                error={err("beneficiary.mobile")} autoComplete="off" />
              <Field label="Email" type="email" value={form.ben_email} onChange={set("ben_email")}
                hint="Optional" error={err("beneficiary.email")} autoComplete="off" />
              <Field label="Street address" value={form.ben_address_line1}
                onChange={set("ben_address_line1")} error={err("beneficiary.address_line1")}
                autoComplete="off" />
              <Field label="Suburb or area" value={form.ben_suburb} onChange={set("ben_suburb")}
                error={err("beneficiary.suburb")} autoComplete="off" />
              <Field label="City or town" value={form.ben_city} onChange={set("ben_city")}
                error={err("beneficiary.city")} autoComplete="off" />
              <Field label="Postal code" value={form.ben_postal_code}
                onChange={set("ben_postal_code")} error={err("beneficiary.postal_code")}
                autoComplete="off" />
            </div>
          )}
        </section>

        <section className="card">
          <div className="card-head"><h2 className="t-section">5. Payment</h2></div>
          <div className="form-grid">
            <Select label="Method" value={form.payment_method} onChange={set("payment_method")}
              options={METHODS} error={err("payment_method")} />
            {IN_PERSON.has(form.payment_method) && (
              <Select label="Branch" value={form.pay_branch_code}
                onChange={set("pay_branch_code")} options={BRANCH_OPTIONS}
                hint="Where they will pay" error={err("pay_branch_code")} />
            )}
            <Select label="Payment frequency" value={form.frequency} onChange={set("frequency")}
              options={onceOff ? ONCE_OFF : FREQUENCIES} disabled={onceOff}
              hint={onceOff ? "This plan is paid once" : undefined} error={err("frequency")} />
            <Select label="Payment day" value={onceOff ? "" : form.payment_day}
              onChange={set("payment_day")} options={PAYMENT_DAYS} disabled={onceOff}
              hint={onceOff ? "Paid once" : "WhatsApp reminds them on this day, and the day after if unpaid"}
              error={err("debit_day")} />
            <div className="field">
              <span className="field-label">Premium</span>
              <div className="premium-readout" aria-live="polite">
                {"cents" in premium ? (
                  <>
                    <strong>{formatMoney(premium.cents)} {PER[form.frequency]}</strong>
                    <span className="t-small muted">{premium.detail}</span>
                  </>
                ) : <span className="t-small muted">{premium.problem}</span>}
              </div>
              <span className="field-hint">Set by the plan. It cannot be typed in.</span>
            </div>
            <div className="field">
              <span className="field-label">Cover</span>
              <div className="premium-readout" aria-live="polite">
                {"cents" in premium ? (
                  premium.cover !== null
                    ? <strong>{formatMoney(premium.cover, premium.currency)}</strong>
                    : <span className="t-small muted">Not on the price list yet</span>
                ) : <span className="t-small muted">{premium.problem}</span>}
              </div>
              <span className="field-hint">Set by the plan. It cannot be typed in.</span>
            </div>
          </div>
          <p className="t-small muted" style={{ marginBottom: 0 }}>
            Debit orders are coming soon. Bank account details are never captured here:
            when debit orders go live, the payment provider takes them.
          </p>
        </section>

        <section className="card">
          <div className="card-head"><h2 className="t-section">6. Notes</h2></div>
          <div className={`field${err("notes") ? " field-error" : ""}`}>
            <label htmlFor="enrol-notes">Notes on this policy</label>
            <textarea id="enrol-notes" rows={Math.max(4, form.notes.split("\n").length + 1)}
              maxLength={4000} value={form.notes} onChange={(e) => set("notes")(e.target.value)}
              aria-describedby="enrol-notes-hint" />
            <span className="field-hint" id="enrol-notes-hint" role={err("notes") ? "alert" : undefined}>
              {err("notes") ?? (enquiry
                ? "Filled in with what the website asked that has no field above. Edit it as needed."
                : "Optional. Shown on the policy page.")}
            </span>
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
