import { useEffect, useState, type FormEvent } from "react";
import {
  ApiError, enrolMember, fetchEnquiry, fetchNextPolicyNumber, fetchPlanPrices,
  type EnquiryDetail, type PayBranch, type PaymentMethod, type PlanPrice,
} from "@/lib/api";
import { SOUTH_AFRICA, WORKING } from "@/lib/compliance";
import { decodeSaId, fullName } from "@/lib/derive";
import { navigate } from "@/lib/router";
import MemberFormSections, {
  BLANK, IN_PERSON, orNull, websiteLabel, type MemberFormValues,
} from "@/components/MemberForm";
import { Button, Notice, Skeleton } from "@/components/ui";

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

type Form = MemberFormValues;

// Debit order is not offered yet, so a family who asked for one on the website
// starts as "not decided" and staff agree another method with them.
const PAYMENT_PREFERENCES = new Set(["eft", "cash", "card", "undecided"]);

/** "Nandi Mkhize" as first names and surname. The surname is the last word. */
const splitName = (name: string | null) => {
  const words = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (words.length < 2) return { first: words[0] ?? "", last: "" };
  return { first: words.slice(0, -1).join(" "), last: words[words.length - 1] };
};

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

  // What the API needs from the form that the form only shows.
  const decoded = decodeSaId(form.id_number);
  const benDob = decodeSaId(form.ben_id_number)?.dob ?? form.ben_date_of_birth;
  const benDecoded = decodeSaId(form.ben_id_number);
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
        <MemberFormSections mode="enrol" form={form} setForm={setForm} errors={errors}
          prices={prices} enquiry={enquiry} />

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
