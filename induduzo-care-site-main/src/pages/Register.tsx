import { useState } from "react";
import { useLanguage } from "@/lib/i18n";
import { NavLink } from "@/lib/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, StepIndicator } from "@/components/form/Field";
import { ArrowRight, Loader2, MessageCircle, Phone, ShieldCheck } from "lucide-react";
import { CONTACT_PHONE_LINK, WHATSAPP_URL } from "@/lib/contact";
import { PLANS } from "@/data/plans";
import {
  RegistrationError,
  isValidEmail,
  isValidMobile,
  normaliseMobile,
  storeEnquiry,
  submitLead,
  type LanguageCode,
  type LeadPayload,
  type PlanCode,
} from "@/lib/registration";

const SELECT_CLASS =
  "flex h-11 w-full rounded-md border border-input bg-background px-3 py-2 text-base " +
  "ring-offset-background focus-visible:outline-none focus-visible:ring-2 " +
  "focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 " +
  "aria-[invalid=true]:border-destructive";

const PROVINCES = [
  "KwaZulu-Natal",
  "Gauteng",
  "Eastern Cape",
  "Western Cape",
  "Free State",
  "Mpumalanga",
  "Limpopo",
  "North West",
  "Northern Cape",
];

const LANGUAGES: { value: LanguageCode; label: string }[] = [
  { value: "zu", label: "isiZulu" },
  { value: "en", label: "English" },
  { value: "xh", label: "isiXhosa" },
  { value: "af", label: "Afrikaans" },
  { value: "st", label: "Sesotho" },
  { value: "other", label: "Other / Okunye" },
];

const HOW_HEARD = [
  "Word of mouth / Family or friend",
  "Facebook",
  "Google search",
  "Radio",
  "Burial society",
  "Church",
  "Induduzo agent",
  "Themba Njilo Foundation",
  "Other",
];

type FormState = {
  first_name: string;
  surname: string;
  mobile_number: string;
  email: string;
  city: string;
  suburb_or_town: string;
  province: string;
  language_preference: LanguageCode;
  plan_interest: PlanCode;
  best_contact_time: string;
  how_heard: string;
  contact_consent: boolean;
  marketing_consent: boolean;
};

const INITIAL: FormState = {
  first_name: "",
  surname: "",
  mobile_number: "",
  email: "",
  city: "",
  suburb_or_town: "",
  province: "KwaZulu-Natal",
  language_preference: "zu",
  plan_interest: "unsure",
  best_contact_time: "",
  how_heard: "",
  contact_consent: false,
  marketing_consent: false,
};

export default function Register() {
  const { language } = useLanguage();
  const en = language === "en";

  const [form, setForm] = useState<FormState>(INITIAL);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    // Clear the error the moment the user starts fixing it, rather than making
    // them resubmit to find out whether they got it right.
    setErrors((prev) => (prev[key] ? { ...prev, [key]: "" } : prev));
  };

  const validate = (): boolean => {
    const next: Record<string, string> = {};
    if (!form.first_name.trim()) {
      next.first_name = en ? "Please enter your name." : "Sicela ufake igama lakho.";
    }
    if (!form.surname.trim()) {
      next.surname = en ? "Please enter your surname." : "Sicela ufake isibongo sakho.";
    }
    if (!form.mobile_number.trim()) {
      next.mobile_number = en
        ? "We need a mobile number to call you back."
        : "Sidinga inombolo yocingo ukuze sikushayele.";
    } else if (!isValidMobile(form.mobile_number)) {
      next.mobile_number = en
        ? "That does not look like a South African mobile number. Example: 082 123 4567"
        : "Lena ayibukeki njengenombolo yaseNingizimu Afrika. Isibonelo: 082 123 4567";
    }
    if (!isValidEmail(form.email)) {
      next.email = en ? "Please check this email address." : "Sicela uhlole leli kheli le-imeyili.";
    }
    if (!form.contact_consent) {
      next.contact_consent = en
        ? "We need your permission before we may contact you."
        : "Sidinga imvume yakho ngaphambi kokuba sixhumane nawe.";
    }
    setErrors(next);

    // Move focus to the first problem so keyboard and screen-reader users are
    // not left guessing why nothing happened.
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
    if (!validate()) return;

    setSubmitting(true);
    const payload: LeadPayload = {
      first_name: form.first_name.trim(),
      surname: form.surname.trim(),
      mobile_number: normaliseMobile(form.mobile_number),
      email: form.email.trim() || undefined,
      city: form.city.trim() || undefined,
      suburb_or_town: form.suburb_or_town.trim() || undefined,
      province: form.province || undefined,
      language_preference: form.language_preference,
      plan_interest: form.plan_interest,
      best_contact_time: form.best_contact_time || undefined,
      how_heard: form.how_heard || undefined,
      contact_consent: form.contact_consent,
      marketing_consent: form.marketing_consent,
    };

    try {
      const handle = await submitLead(payload);
      storeEnquiry(handle);
      window.history.pushState({}, "", "/register/details");
      window.dispatchEvent(new PopStateEvent("popstate"));
      window.scrollTo({ top: 0 });
    } catch (error) {
      if (error instanceof RegistrationError) {
        setSubmitError(error.message);
        if (Object.keys(error.fieldErrors).length) setErrors(error.fieldErrors);
      } else {
        setSubmitError(
          en
            ? "Something went wrong. Please phone or WhatsApp us and we will help you."
            : "Kukhona okungahambanga kahle. Sicela usishayele noma usithumele nge-WhatsApp.",
        );
      }
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col">
      <section className="border-b-2 border-accent bg-parchment py-12 md:py-16">
        <div className="container">
          <div className="mx-auto max-w-2xl">
            <h1 className="mb-4">{en ? "Register your interest" : "Bhalisa isifiso sakho"}</h1>
            <p className="text-lg text-muted-foreground">
              {en
                ? "Step one takes about a minute. Give us your name and number and we will call you back with a quote — you are not signing up to anything yet."
                : "Isinyathelo sokuqala sithatha umzuzu. Sinike igama nenombolo yakho sizokushayela — awukabhalisi lutho okwamanje."}
            </p>
          </div>
        </div>
      </section>

      <section className="py-12">
        <div className="container">
          <div className="mx-auto max-w-2xl">
            <StepIndicator
              current={1}
              labels={
                en
                  ? ["Your details", "Cover details"]
                  : ["Imininingwane yakho", "Imininingwane yokumbozwa"]
              }
            />

            {submitError && (
              <div
                role="alert"
                className="mb-6 rounded-lg border-2 border-destructive bg-destructive/5 p-4"
              >
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

            <Card>
              <CardContent className="p-5 sm:p-8">
                {/* A real form element with autoComplete on: this is what lets the
                    browser and Google offer saved name/phone/address values. */}
                <form onSubmit={handleSubmit} noValidate autoComplete="on">
                  <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
                    <Field
                      label={en ? "Name" : "Igama"}
                      required
                      error={errors.first_name}
                    >
                      {(props) => (
                        <Input
                          {...props}
                          data-field="first_name"
                          name="given-name"
                          autoComplete="given-name"
                          autoCapitalize="words"
                          value={form.first_name}
                          onChange={(e) => set("first_name", e.target.value)}
                        />
                      )}
                    </Field>

                    <Field label={en ? "Surname" : "Isibongo"} required error={errors.surname}>
                      {(props) => (
                        <Input
                          {...props}
                          data-field="surname"
                          name="family-name"
                          autoComplete="family-name"
                          autoCapitalize="words"
                          value={form.surname}
                          onChange={(e) => set("surname", e.target.value)}
                        />
                      )}
                    </Field>

                    <Field
                      label={en ? "Mobile number" : "Inombolo yocingo"}
                      required
                      error={errors.mobile_number}
                      hint={en ? "We will call or WhatsApp this number." : "Sizoshayela noma sithumele i-WhatsApp kule nombolo."}
                    >
                      {(props) => (
                        <Input
                          {...props}
                          data-field="mobile_number"
                          name="tel"
                          type="tel"
                          inputMode="tel"
                          autoComplete="tel"
                          placeholder="082 123 4567"
                          value={form.mobile_number}
                          onChange={(e) => set("mobile_number", e.target.value)}
                        />
                      )}
                    </Field>

                    <Field label={en ? "Email address" : "Ikheli le-imeyili"} error={errors.email}>
                      {(props) => (
                        <Input
                          {...props}
                          data-field="email"
                          name="email"
                          type="email"
                          inputMode="email"
                          autoComplete="email"
                          value={form.email}
                          onChange={(e) => set("email", e.target.value)}
                        />
                      )}
                    </Field>

                    <Field label={en ? "City / Town" : "Idolobha"}>
                      {(props) => (
                        <Input
                          {...props}
                          name="address-level2"
                          autoComplete="address-level2"
                          placeholder="Pietermaritzburg"
                          value={form.city}
                          onChange={(e) => set("city", e.target.value)}
                        />
                      )}
                    </Field>

                    <Field label={en ? "Suburb / Area" : "Indawo"}>
                      {(props) => (
                        <Input
                          {...props}
                          name="address-level3"
                          autoComplete="address-level3"
                          placeholder="Edendale"
                          value={form.suburb_or_town}
                          onChange={(e) => set("suburb_or_town", e.target.value)}
                        />
                      )}
                    </Field>

                    <Field label={en ? "Province" : "Isifundazwe"}>
                      {(props) => (
                        <select
                          {...props}
                          name="address-level1"
                          autoComplete="address-level1"
                          className={SELECT_CLASS}
                          value={form.province}
                          onChange={(e) => set("province", e.target.value)}
                        >
                          {PROVINCES.map((p) => (
                            <option key={p} value={p}>
                              {p}
                            </option>
                          ))}
                        </select>
                      )}
                    </Field>

                    <Field
                      label={en ? "Preferred language" : "Ulimi olukhethayo"}
                      hint={en ? "So we speak to you in your own language." : "Ukuze sikhulume nawe ngolimi lwakho."}
                    >
                      {(props) => (
                        <select
                          {...props}
                          name="language"
                          className={SELECT_CLASS}
                          value={form.language_preference}
                          onChange={(e) => set("language_preference", e.target.value as LanguageCode)}
                        >
                          {LANGUAGES.map((l) => (
                            <option key={l.value} value={l.value}>
                              {l.label}
                            </option>
                          ))}
                        </select>
                      )}
                    </Field>

                    <Field
                      label={en ? "Which plan interests you?" : "Yiluphi uhlelo olukuthandayo?"}
                      className="sm:col-span-2"
                    >
                      {(props) => (
                        <select
                          {...props}
                          name="plan"
                          className={SELECT_CLASS}
                          value={form.plan_interest}
                          onChange={(e) => set("plan_interest", e.target.value as PlanCode)}
                        >
                          <option value="unsure">
                            {en ? "I am not sure yet — please advise me" : "Angikaqiniseki — ngicela ningeluleke"}
                          </option>
                          {PLANS.map((plan) => (
                            <option key={plan.id} value={plan.id.replace("-", "_")}>
                              {plan.name[language]} — {plan.price} {plan.period[language]}
                            </option>
                          ))}
                        </select>
                      )}
                    </Field>

                    <Field label={en ? "Best time to call" : "Isikhathi esihle sokushayela"}>
                      {(props) => (
                        <select
                          {...props}
                          name="best-contact-time"
                          className={SELECT_CLASS}
                          value={form.best_contact_time}
                          onChange={(e) => set("best_contact_time", e.target.value)}
                        >
                          <option value="">{en ? "Any time" : "Nanoma yinini"}</option>
                          <option value="morning">{en ? "Morning (8am–12pm)" : "Ekuseni (8–12)"}</option>
                          <option value="afternoon">{en ? "Afternoon (12pm–5pm)" : "Emini (12–5)"}</option>
                          <option value="evening">{en ? "Evening (5pm–8pm)" : "Ntambama (5–8)"}</option>
                        </select>
                      )}
                    </Field>

                    <Field label={en ? "How did you hear about us?" : "Uzwe kanjani ngathi?"}>
                      {(props) => (
                        <select
                          {...props}
                          name="how-heard"
                          className={SELECT_CLASS}
                          value={form.how_heard}
                          onChange={(e) => set("how_heard", e.target.value)}
                        >
                          <option value="">{en ? "Please choose" : "Sicela ukhethe"}</option>
                          {HOW_HEARD.map((h) => (
                            <option key={h} value={h}>
                              {h}
                            </option>
                          ))}
                        </select>
                      )}
                    </Field>
                  </div>

                  {/* Consent. POPIA requires this to be a deliberate act, so both
                      boxes start unticked and marketing is separate from contact. */}
                  <fieldset className="mt-8 rounded-lg border bg-secondary/30 p-5">
                    <legend className="px-2 text-sm font-semibold">
                      {en ? "Your privacy" : "Ubumfihlo bakho"}
                    </legend>

                    <div className="space-y-4">
                      <div className="flex items-start gap-3">
                        <Checkbox
                          id="contact_consent"
                          data-field="contact_consent"
                          checked={form.contact_consent}
                          onCheckedChange={(v) => set("contact_consent", v === true)}
                          aria-invalid={Boolean(errors.contact_consent)}
                          aria-describedby={errors.contact_consent ? "contact_consent-error" : undefined}
                          className="mt-1"
                        />
                        <label htmlFor="contact_consent" className="text-sm leading-relaxed">
                          {en
                            ? "I agree that Induduzo Funeral Home may contact me about funeral cover using the details above."
                            : "Ngiyavuma ukuthi i-Induduzo Funeral Home ingaxhumana nami mayelana nokumbozwa komngcwabo isebenzisa imininingwane engenhla."}
                          <span className="ml-1 text-primary" aria-hidden="true">*</span>
                        </label>
                      </div>
                      {errors.contact_consent && (
                        <p id="contact_consent-error" role="alert" className="text-sm font-medium text-destructive">
                          {errors.contact_consent}
                        </p>
                      )}

                      <div className="flex items-start gap-3">
                        <Checkbox
                          id="marketing_consent"
                          checked={form.marketing_consent}
                          onCheckedChange={(v) => set("marketing_consent", v === true)}
                          className="mt-1"
                        />
                        <label htmlFor="marketing_consent" className="text-sm leading-relaxed">
                          {en
                            ? "I would also like to receive news and special offers. (Optional)"
                            : "Ngingathanda futhi ukuthola izindaba nokunikezwa okukhethekile. (Ngokuzikhethela)"}
                        </label>
                      </div>

                      <p className="flex items-start gap-2 pt-1 text-xs text-muted-foreground">
                        <ShieldCheck className="mt-0.5 h-4 w-4 flex-shrink-0" aria-hidden="true" />
                        <span>
                          {en
                            ? "We keep your details private and POPIA-compliant. We never ask for bank or card details on this website."
                            : "Sigcina imininingwane yakho iyimfihlo futhi ihambisana ne-POPIA. Asikaze sicele imininingwane yebhange noma yekhadi kule webhusayithi."}
                        </span>
                      </p>
                    </div>
                  </fieldset>

                  <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
                    <Button type="submit" size="lg" disabled={submitting} className="sm:flex-1">
                      {submitting ? (
                        <>
                          <Loader2 className="mr-2 h-5 w-5 animate-spin" aria-hidden="true" />
                          {en ? "Sending…" : "Iyathumela…"}
                        </>
                      ) : (
                        <>
                          {en ? "Continue" : "Qhubeka"}
                          <ArrowRight className="ml-2 h-5 w-5" aria-hidden="true" />
                        </>
                      )}
                    </Button>
                    <Button type="button" size="lg" variant="outline" asChild>
                      <NavLink to="/join">{en ? "Back to plans" : "Buyela ezinhlelweni"}</NavLink>
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>

            <p className="mt-6 text-center text-sm text-muted-foreground">
              {en
                ? "Would you rather talk to someone? "
                : "Ungathanda ukukhuluma nomuntu? "}
              <a href={CONTACT_PHONE_LINK} className="font-semibold text-primary underline">
                {en ? "Call us any time" : "Sishayele nanoma nini"}
              </a>
              {" · "}
              <a
                href={WHATSAPP_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="font-semibold text-primary underline"
              >
                WhatsApp
              </a>
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
