import { useEffect, useMemo, useState } from "react";
import { useLanguage } from "@/lib/i18n";
import { NavLink } from "@/lib/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, StepIndicator } from "@/components/form/Field";
import { CheckCircle2, Loader2, MessageCircle, Phone, ShieldCheck } from "lucide-react";
import { CONTACT_PHONE_LINK, WHATSAPP_URL } from "@/lib/contact";
import { PLANS } from "@/data/plans";
import {
  RegistrationError,
  clearEnquiry,
  dobFromSaId,
  isValidMobile,
  isValidSaId,
  loadEnquiry,
  normaliseMobile,
  submitApplication,
  type ApplicationPayload,
  type CoffinOption,
  type CoverArea,
  type EnquiryHandle,
  type MaritalStatus,
  type PaymentPreference,
  type PlanCode,
} from "@/lib/registration";

const SELECT_CLASS =
  "flex h-11 w-full rounded-md border border-input bg-background px-3 py-2 text-base " +
  "ring-offset-background focus-visible:outline-none focus-visible:ring-2 " +
  "focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 " +
  "aria-[invalid=true]:border-destructive";

type FormState = {
  id_number: string;
  date_of_birth: string;
  marital_status: MaritalStatus | "";
  address_line1: string;
  address_line2: string;
  postal_code: string;
  cover_area: CoverArea | "";
  plan_selected: PlanCode | "";
  coffin_choice: CoffinOption | "";
  number_of_dependants: string;
  next_of_kin_name: string;
  next_of_kin_mobile: string;
  next_of_kin_relationship: string;
  beneficiary_name: string;
  beneficiary_mobile: string;
  beneficiary_relationship: string;
  payment_preference: PaymentPreference | "";
  notes: string;
  terms_accepted: boolean;
};

const INITIAL: FormState = {
  id_number: "",
  date_of_birth: "",
  marital_status: "",
  address_line1: "",
  address_line2: "",
  postal_code: "",
  cover_area: "",
  plan_selected: "",
  coffin_choice: "",
  number_of_dependants: "",
  next_of_kin_name: "",
  next_of_kin_mobile: "",
  next_of_kin_relationship: "",
  beneficiary_name: "",
  beneficiary_mobile: "",
  beneficiary_relationship: "",
  payment_preference: "",
  notes: "",
  terms_accepted: false,
};

export default function RegisterDetails() {
  const { language } = useLanguage();
  const en = language === "en";

  const [handle, setHandle] = useState<EnquiryHandle | null>(null);
  const [form, setForm] = useState<FormState>(INITIAL);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState<EnquiryHandle | null>(null);

  // Step 1 already ran and gave us a server-side row. Carry it forward, and
  // pre-select the plan they said they were interested in.
  useEffect(() => {
    const stored = loadEnquiry();
    if (!stored) {
      window.history.replaceState({}, "", "/register");
      window.dispatchEvent(new PopStateEvent("popstate"));
      return;
    }
    setHandle(stored);
    if (stored.plan_interest && stored.plan_interest !== "unsure") {
      setForm((prev) => ({
        ...prev,
        plan_selected: stored.plan_interest,
        cover_area:
          stored.plan_interest === "plan_a"
            ? "edolobheni"
            : stored.plan_interest === "plan_b"
              ? "emakhaya"
              : "",
      }));
    }
  }, []);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setErrors((prev) => (prev[key] ? { ...prev, [key]: "" } : prev));
  };

  // A valid SA ID already contains the date of birth. Deriving it means one
  // less field to mistype, and it silently confirms the ID was entered right.
  const handleIdChange = (value: string) => {
    set("id_number", value);
    const dob = dobFromSaId(value);
    if (dob) setForm((prev) => ({ ...prev, date_of_birth: dob }));
  };

  const isPlanC = form.plan_selected === "plan_c";

  const validate = (): boolean => {
    const next: Record<string, string> = {};

    if (!form.id_number.trim()) {
      next.id_number = en ? "We need your ID number to open a policy." : "Sidinga inombolo yakho yomazisi.";
    } else if (!isValidSaId(form.id_number)) {
      next.id_number = en
        ? "That ID number is not valid. Please check all 13 digits."
        : "Lo mazisi awulungile. Sicela uhlole zonke izinombolo eziyi-13.";
    }
    if (!form.address_line1.trim()) {
      next.address_line1 = en ? "Please give us a street address." : "Sicela usinike ikheli lomgwaqo.";
    }
    if (!form.plan_selected) {
      next.plan_selected = en ? "Please choose a plan." : "Sicela ukhethe uhlelo.";
    }
    if (!form.cover_area) {
      next.cover_area = en ? "Please tell us where the burial would be." : "Sicela usitshele ukuthi umngcwabo uzoba kuphi.";
    }
    if (isPlanC && !form.coffin_choice) {
      next.coffin_choice = en ? "Plan C needs a coffin choice." : "Uhlelo C ludinga ukukhetha ibhokisi.";
    }
    if (form.next_of_kin_mobile && !isValidMobile(form.next_of_kin_mobile)) {
      next.next_of_kin_mobile = en ? "Please check this mobile number." : "Sicela uhlole le nombolo.";
    }
    if (form.beneficiary_mobile && !isValidMobile(form.beneficiary_mobile)) {
      next.beneficiary_mobile = en ? "Please check this mobile number." : "Sicela uhlole le nombolo.";
    }
    if (!form.terms_accepted) {
      next.terms_accepted = en
        ? "Please accept the terms to submit your application."
        : "Sicela wamukele imigomo ukuze uthumele isicelo sakho.";
    }

    setErrors(next);
    const firstKey = Object.keys(next)[0];
    if (firstKey) {
      const el = document.querySelector<HTMLElement>(`[data-field="${firstKey}"]`);
      el?.focus();
      el?.scrollIntoView({ block: "center", behavior: "smooth" });
    }
    return Object.keys(next).length === 0;
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitError(null);
    if (!handle || !validate()) return;

    setSubmitting(true);
    const payload: ApplicationPayload = {
      id_number: form.id_number.replace(/\s/g, ""),
      date_of_birth: form.date_of_birth || undefined,
      marital_status: form.marital_status || undefined,
      address_line1: form.address_line1.trim(),
      address_line2: form.address_line2.trim() || undefined,
      postal_code: form.postal_code.trim() || undefined,
      cover_area: form.cover_area || undefined,
      plan_selected: form.plan_selected || undefined,
      coffin_choice: form.coffin_choice || undefined,
      number_of_dependants: form.number_of_dependants ? Number(form.number_of_dependants) : undefined,
      next_of_kin_name: form.next_of_kin_name.trim() || undefined,
      next_of_kin_mobile: form.next_of_kin_mobile ? normaliseMobile(form.next_of_kin_mobile) : undefined,
      next_of_kin_relationship: form.next_of_kin_relationship.trim() || undefined,
      beneficiary_name: form.beneficiary_name.trim() || undefined,
      beneficiary_mobile: form.beneficiary_mobile ? normaliseMobile(form.beneficiary_mobile) : undefined,
      beneficiary_relationship: form.beneficiary_relationship.trim() || undefined,
      payment_preference: form.payment_preference || undefined,
      notes: form.notes.trim() || undefined,
      terms_accepted: true,
    };

    try {
      const result = await submitApplication(handle.id, payload);
      clearEnquiry();
      setDone(result);
      window.scrollTo({ top: 0 });
    } catch (error) {
      if (error instanceof RegistrationError) {
        setSubmitError(error.message);
        if (Object.keys(error.fieldErrors).length) setErrors(error.fieldErrors);
      } else {
        setSubmitError(en ? "Something went wrong. Please phone us." : "Kukhona okungahambanga kahle. Sicela usishayele.");
      }
      setSubmitting(false);
    }
  };

  const selectedPlan = useMemo(
    () => PLANS.find((p) => p.id.replace("-", "_") === form.plan_selected),
    [form.plan_selected],
  );

  // ---------------------------------------------------------------- success
  if (done) {
    return (
      <div className="flex flex-col">
        <section className="py-16">
          <div className="container">
            <Card className="mx-auto max-w-2xl">
              <CardContent className="p-6 text-center sm:p-10">
                <span className="mx-auto mb-6 inline-flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
                  <CheckCircle2 className="h-8 w-8 text-primary" aria-hidden="true" />
                </span>
                <h1 className="mb-4 text-3xl">
                  {en ? "Application received" : "Isicelo sitholakele"}
                </h1>
                <p className="mb-2 text-lg text-muted-foreground">
                  {en ? "Thank you, " : "Siyabonga, "}
                  {done.first_name}. {en ? "Your reference is" : "Inkomba yakho ithi"}
                </p>
                <p className="mb-8 text-2xl font-bold text-primary">{done.reference}</p>

                <div className="mb-8 rounded-lg border bg-secondary/30 p-5 text-left">
                  <h2 className="mb-3 text-lg font-semibold">
                    {en ? "What happens next" : "Okulandelayo"}
                  </h2>
                  <ol className="space-y-2 text-base">
                    <li>
                      1. {en
                        ? "We send a WhatsApp confirmation to your number."
                        : "Sithumela isiqinisekiso se-WhatsApp kunombolo yakho."}
                    </li>
                    <li>
                      2. {en
                        ? "A family liaison calls you within one working day to confirm your details."
                        : "Umxhumanisi womndeni uzokushayela phakathi nosuku olulodwa lomsebenzi."}
                    </li>
                    <li>
                      3. {en
                        ? "We arrange your first premium payment with you directly. Your 3-month waiting period starts from your first payment."
                        : "Sihlela nawe inkokhelo yakho yokuqala. Isikhathi sokulinda sezinyanga ezi-3 siqala enkokhelweni yakho yokuqala."}
                    </li>
                  </ol>
                </div>

                <p className="mb-6 text-sm text-muted-foreground">
                  {en
                    ? "We will never ask for your bank card details over the phone or by SMS."
                    : "Asisoze sicele imininingwane yekhadi lakho lasebhange ngocingo noma nge-SMS."}
                </p>

                <div className="flex flex-wrap justify-center gap-3">
                  <Button asChild>
                    <a href={CONTACT_PHONE_LINK}>
                      <Phone className="mr-2 h-4 w-4" />
                      {en ? "Call us" : "Sishayele"}
                    </a>
                  </Button>
                  <Button variant="outline" asChild>
                    <NavLink to="/">{en ? "Back to home" : "Buyela ekhaya"}</NavLink>
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        </section>
      </div>
    );
  }

  if (!handle) return null;

  // ----------------------------------------------------------------- form
  return (
    <div className="flex flex-col">
      <section className="border-b-2 border-accent bg-parchment py-12 md:py-16">
        <div className="container">
          <div className="mx-auto max-w-2xl">
            <h1 className="mb-4">{en ? "Complete your application" : "Qedela isicelo sakho"}</h1>
            <p className="text-lg text-muted-foreground">
              {en
                ? "Almost there. These are the details we need to open your policy."
                : "Sesizofika. Nansi imininingwane esiyidingayo ukuze sivule inqubomgomo yakho."}
            </p>
          </div>
        </div>
      </section>

      <section className="py-12">
        <div className="container">
          <div className="mx-auto max-w-2xl">
            <StepIndicator
              current={2}
              labels={
                en
                  ? ["Your details", "Cover details"]
                  : ["Imininingwane yakho", "Imininingwane yokumbozwa"]
              }
            />

            {/* Carried forward from step 1, so nobody retypes what they just gave us. */}
            <div className="mb-6 rounded-lg border-2 border-accent bg-accent/5 p-4">
              <p className="text-sm text-muted-foreground">
                {en ? "Continuing for" : "Kuqhutshekwa ku-"}
              </p>
              <p className="font-semibold">
                {handle.first_name} {handle.surname} · {handle.mobile_number}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                {en ? "Reference" : "Inkomba"}: <span className="font-mono">{handle.reference}</span>
                {" · "}
                <NavLink to="/register" className="underline">
                  {en ? "Change" : "Shintsha"}
                </NavLink>
              </p>
            </div>

            {submitError && (
              <div role="alert" className="mb-6 rounded-lg border-2 border-destructive bg-destructive/5 p-4">
                <p className="font-medium text-destructive">{submitError}</p>
                <div className="mt-3 flex flex-wrap gap-3">
                  <Button size="sm" variant="outline" asChild>
                    <a href={CONTACT_PHONE_LINK}>
                      <Phone className="mr-2 h-4 w-4" />
                      {en ? "Call us" : "Sishayele"}
                    </a>
                  </Button>
                  <Button size="sm" variant="outline" asChild>
                    <a href={WHATSAPP_URL} target="_blank" rel="noopener noreferrer">
                      <MessageCircle className="mr-2 h-4 w-4" />
                      WhatsApp
                    </a>
                  </Button>
                </div>
              </div>
            )}

            <form onSubmit={handleSubmit} noValidate autoComplete="on">
              <Card className="mb-6">
                <CardContent className="p-5 sm:p-8">
                  <h2 className="mb-5 text-xl font-semibold">
                    {en ? "About you" : "Ngawe"}
                  </h2>
                  <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                    <Field
                      label={en ? "ID number" : "Inombolo yomazisi"}
                      required
                      error={errors.id_number}
                      hint={en ? "13 digits. We use this to confirm your date of birth." : "Izinombolo eziyi-13."}
                    >
                      {(props) => (
                        <Input
                          {...props}
                          data-field="id_number"
                          name="id-number"
                          inputMode="numeric"
                          maxLength={13}
                          placeholder="8001015009087"
                          value={form.id_number}
                          onChange={(e) => handleIdChange(e.target.value.replace(/[^0-9]/g, ""))}
                        />
                      )}
                    </Field>

                    <Field
                      label={en ? "Date of birth" : "Usuku lokuzalwa"}
                      hint={en ? "Filled in from your ID number." : "Igcwaliswa kusuka kumazisi wakho."}
                    >
                      {(props) => (
                        <Input
                          {...props}
                          name="bday"
                          type="date"
                          autoComplete="bday"
                          value={form.date_of_birth}
                          onChange={(e) => set("date_of_birth", e.target.value)}
                        />
                      )}
                    </Field>

                    <Field label={en ? "Marital status" : "Isimo somshado"}>
                      {(props) => (
                        <select
                          {...props}
                          className={SELECT_CLASS}
                          value={form.marital_status}
                          onChange={(e) => set("marital_status", e.target.value as MaritalStatus)}
                        >
                          <option value="">{en ? "Please choose" : "Sicela ukhethe"}</option>
                          <option value="single">{en ? "Single" : "Awushadile"}</option>
                          <option value="married">{en ? "Married" : "Ushadile"}</option>
                          <option value="customary_union">{en ? "Customary union" : "Umshado wesintu"}</option>
                          <option value="divorced">{en ? "Divorced" : "Udivosile"}</option>
                          <option value="widowed">{en ? "Widowed" : "Umfelokazi"}</option>
                          <option value="other">{en ? "Other" : "Okunye"}</option>
                        </select>
                      )}
                    </Field>

                    <Field
                      label={en ? "Number of dependants" : "Inani labancikile"}
                      hint={en ? "People you want covered with you." : "Abantu ofuna bambozwe nawe."}
                    >
                      {(props) => (
                        <Input
                          {...props}
                          type="number"
                          inputMode="numeric"
                          min={0}
                          max={20}
                          value={form.number_of_dependants}
                          onChange={(e) => set("number_of_dependants", e.target.value)}
                        />
                      )}
                    </Field>

                    <Field
                      label={en ? "Street address" : "Ikheli lomgwaqo"}
                      required
                      error={errors.address_line1}
                      className="sm:col-span-2"
                    >
                      {(props) => (
                        <Input
                          {...props}
                          data-field="address_line1"
                          name="address-line1"
                          autoComplete="address-line1"
                          value={form.address_line1}
                          onChange={(e) => set("address_line1", e.target.value)}
                        />
                      )}
                    </Field>

                    <Field label={en ? "Address line 2" : "Umugqa wesibili wekheli"}>
                      {(props) => (
                        <Input
                          {...props}
                          name="address-line2"
                          autoComplete="address-line2"
                          value={form.address_line2}
                          onChange={(e) => set("address_line2", e.target.value)}
                        />
                      )}
                    </Field>

                    <Field label={en ? "Postal code" : "Ikhodi yeposi"}>
                      {(props) => (
                        <Input
                          {...props}
                          name="postal-code"
                          autoComplete="postal-code"
                          inputMode="numeric"
                          maxLength={4}
                          placeholder="3201"
                          value={form.postal_code}
                          onChange={(e) => set("postal_code", e.target.value.replace(/[^0-9]/g, ""))}
                        />
                      )}
                    </Field>
                  </div>
                </CardContent>
              </Card>

              <Card className="mb-6">
                <CardContent className="p-5 sm:p-8">
                  <h2 className="mb-5 text-xl font-semibold">{en ? "Your cover" : "Ukumbozwa kwakho"}</h2>
                  <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                    <Field
                      label={en ? "Plan" : "Uhlelo"}
                      required
                      error={errors.plan_selected}
                      className="sm:col-span-2"
                    >
                      {(props) => (
                        <select
                          {...props}
                          data-field="plan_selected"
                          className={SELECT_CLASS}
                          value={form.plan_selected}
                          onChange={(e) => set("plan_selected", e.target.value as PlanCode)}
                        >
                          <option value="">{en ? "Please choose a plan" : "Sicela ukhethe uhlelo"}</option>
                          {PLANS.map((plan) => (
                            <option key={plan.id} value={plan.id.replace("-", "_")}>
                              {plan.name[language]} — {plan.price} {plan.period[language]}
                            </option>
                          ))}
                        </select>
                      )}
                    </Field>

                    {selectedPlan && (
                      <p className="-mt-2 text-sm text-muted-foreground sm:col-span-2">
                        {selectedPlan.summary[language]}
                      </p>
                    )}

                    <Field
                      label={en ? "Where would the burial be?" : "Umngcwabo ungaba kuphi?"}
                      required
                      error={errors.cover_area}
                    >
                      {(props) => (
                        <select
                          {...props}
                          data-field="cover_area"
                          className={SELECT_CLASS}
                          value={form.cover_area}
                          onChange={(e) => set("cover_area", e.target.value as CoverArea)}
                        >
                          <option value="">{en ? "Please choose" : "Sicela ukhethe"}</option>
                          <option value="edolobheni">{en ? "Edolobheni (City)" : "Edolobheni"}</option>
                          <option value="emakhaya">{en ? "Emakhaya (Rural)" : "Emakhaya"}</option>
                        </select>
                      )}
                    </Field>

                    {isPlanC && (
                      <Field
                        label={en ? "Coffin option" : "Inketho yebhokisi"}
                        required
                        error={errors.coffin_choice}
                      >
                        {(props) => (
                          <select
                            {...props}
                            data-field="coffin_choice"
                            className={SELECT_CLASS}
                            value={form.coffin_choice}
                            onChange={(e) => set("coffin_choice", e.target.value as CoffinOption)}
                          >
                            <option value="">{en ? "Please choose" : "Sicela ukhethe"}</option>
                            <option value="flat_lid">{en ? "Flat lid" : "I-Flat lid"}</option>
                            <option value="casket">{en ? "Casket" : "Ibhokisi"}</option>
                          </select>
                        )}
                      </Field>
                    )}

                    <Field
                      label={en ? "How would you like to pay?" : "Ungathanda ukukhokha kanjani?"}
                      hint={
                        en
                          ? "A preference only — we confirm this with you on the call."
                          : "Okuthandwayo kuphela — sizoqinisekisa lokhu nawe ocingweni."
                      }
                    >
                      {(props) => (
                        <select
                          {...props}
                          className={SELECT_CLASS}
                          value={form.payment_preference}
                          onChange={(e) => set("payment_preference", e.target.value as PaymentPreference)}
                        >
                          <option value="">{en ? "Not sure yet" : "Angikaqiniseki"}</option>
                          <option value="debit_order">{en ? "Debit order" : "I-debit order"}</option>
                          <option value="eft">EFT</option>
                          <option value="cash">{en ? "Cash at the branch" : "Ukheshi egatsheni"}</option>
                          <option value="card">{en ? "Card" : "Ikhadi"}</option>
                        </select>
                      )}
                    </Field>
                  </div>
                </CardContent>
              </Card>

              <Card className="mb-6">
                <CardContent className="p-5 sm:p-8">
                  <h2 className="mb-2 text-xl font-semibold">
                    {en ? "Next of kin & beneficiary" : "Owakwakho nozothola inzuzo"}
                  </h2>
                  <p className="mb-5 text-sm text-muted-foreground">
                    {en
                      ? "Who we should contact, and who receives the payout. You can change these later."
                      : "Ubani okufanele sixhumane naye, nokuthi ubani othola imali. Ungakushintsha lokhu kamuva."}
                  </p>
                  <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                    <Field label={en ? "Next of kin name" : "Igama lowakwakho"}>
                      {(props) => (
                        <Input
                          {...props}
                          value={form.next_of_kin_name}
                          onChange={(e) => set("next_of_kin_name", e.target.value)}
                        />
                      )}
                    </Field>

                    <Field
                      label={en ? "Next of kin mobile" : "Inombolo yowakwakho"}
                      error={errors.next_of_kin_mobile}
                    >
                      {(props) => (
                        <Input
                          {...props}
                          data-field="next_of_kin_mobile"
                          type="tel"
                          inputMode="tel"
                          placeholder="082 123 4567"
                          value={form.next_of_kin_mobile}
                          onChange={(e) => set("next_of_kin_mobile", e.target.value)}
                        />
                      )}
                    </Field>

                    <Field label={en ? "Relationship" : "Ubudlelwano"} className="sm:col-span-2">
                      {(props) => (
                        <Input
                          {...props}
                          placeholder={en ? "Spouse, son, daughter…" : "Umlingani, indodana, indodakazi…"}
                          value={form.next_of_kin_relationship}
                          onChange={(e) => set("next_of_kin_relationship", e.target.value)}
                        />
                      )}
                    </Field>

                    <Field label={en ? "Beneficiary name" : "Igama lozothola inzuzo"}>
                      {(props) => (
                        <Input
                          {...props}
                          value={form.beneficiary_name}
                          onChange={(e) => set("beneficiary_name", e.target.value)}
                        />
                      )}
                    </Field>

                    <Field
                      label={en ? "Beneficiary mobile" : "Inombolo yozothola inzuzo"}
                      error={errors.beneficiary_mobile}
                    >
                      {(props) => (
                        <Input
                          {...props}
                          data-field="beneficiary_mobile"
                          type="tel"
                          inputMode="tel"
                          placeholder="082 123 4567"
                          value={form.beneficiary_mobile}
                          onChange={(e) => set("beneficiary_mobile", e.target.value)}
                        />
                      )}
                    </Field>

                    <Field label={en ? "Beneficiary relationship" : "Ubudlelwano bozothola inzuzo"} className="sm:col-span-2">
                      {(props) => (
                        <Input
                          {...props}
                          value={form.beneficiary_relationship}
                          onChange={(e) => set("beneficiary_relationship", e.target.value)}
                        />
                      )}
                    </Field>

                    <Field label={en ? "Anything else we should know?" : "Kukhona okunye okufanele sikwazi?"} className="sm:col-span-2">
                      {(props) => (
                        <Textarea
                          {...props}
                          rows={3}
                          value={form.notes}
                          onChange={(e) => set("notes", e.target.value)}
                        />
                      )}
                    </Field>
                  </div>
                </CardContent>
              </Card>

              <Card className="mb-6">
                <CardContent className="p-5 sm:p-8">
                  <div className="flex items-start gap-3">
                    <Checkbox
                      id="terms_accepted"
                      data-field="terms_accepted"
                      checked={form.terms_accepted}
                      onCheckedChange={(v) => set("terms_accepted", v === true)}
                      aria-invalid={Boolean(errors.terms_accepted)}
                      aria-describedby={errors.terms_accepted ? "terms-error" : undefined}
                      className="mt-1"
                    />
                    <label htmlFor="terms_accepted" className="text-sm leading-relaxed">
                      {en
                        ? "I confirm the details above are true and correct, and I accept Induduzo Funeral Home's plan terms, including the 3-month waiting period."
                        : "Ngiyaqinisekisa ukuthi imininingwane engenhla iyiqiniso, futhi ngiyayamukela imigomo yohlelo lwe-Induduzo Funeral Home, kufaka isikhathi sokulinda sezinyanga ezi-3."}
                      <span className="ml-1 text-primary" aria-hidden="true">*</span>
                    </label>
                  </div>
                  {errors.terms_accepted && (
                    <p id="terms-error" role="alert" className="mt-2 text-sm font-medium text-destructive">
                      {errors.terms_accepted}
                    </p>
                  )}

                  <p className="mt-4 flex items-start gap-2 text-xs text-muted-foreground">
                    <ShieldCheck className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
                    <span>
                      {en
                        ? "We do not collect bank or card details on this website. Payment is arranged separately once your application is reviewed."
                        : "Asiqoqi imininingwane yebhange noma yekhadi kule webhusayithi. Inkokhelo ihlelwa ngokwehlukene."}
                    </span>
                  </p>
                </CardContent>
              </Card>

              <div className="flex flex-col gap-3 sm:flex-row">
                <Button type="submit" size="lg" disabled={submitting} className="sm:flex-1">
                  {submitting ? (
                    <>
                      <Loader2 className="mr-2 h-5 w-5 animate-spin" aria-hidden="true" />
                      {en ? "Submitting…" : "Iyathumela…"}
                    </>
                  ) : (
                    <>{en ? "Submit application" : "Thumela isicelo"}</>
                  )}
                </Button>
                <Button type="button" size="lg" variant="outline" asChild>
                  <NavLink to="/register">{en ? "Back" : "Emuva"}</NavLink>
                </Button>
              </div>
            </form>
          </div>
        </div>
      </section>
    </div>
  );
}
