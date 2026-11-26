import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Star } from "lucide-react";

import { BrandLogo } from "@/components/BrandLogo";
import { Field } from "@/components/form/Field";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { TWENTY_FOUR_HOUR_LINE } from "@/lib/contact";
import { useLanguage, type Language } from "@/lib/i18n";
import { isValidMobile, normaliseMobile } from "@/lib/registration";
import {
  fetchQuestionnaire,
  sendFeedback,
  sendRating,
  SiteError,
  type FeedbackQuestion,
} from "@/lib/site";
import NotFound from "./NotFound";

/**
 * The private feedback questionnaire, at /feedback/<code>.
 *
 * Not linked from anywhere on the site, not in the sitemap, disallowed in
 * robots.txt and marked noindex. It opens only from its own link, which the
 * office shares and prints as a QR code (Settings > Website settings in the
 * portal). A wrong or retired code shows the site's ordinary 404.
 *
 * Name, surname and number first; then the questions one at a time, which is
 * kinder on a phone held after a scan; then thanks, and the 1-5 rating. The
 * answers are saved before the rating is asked, so leaving at that point still
 * counts.
 *
 * isiZulu wording here is a first draft for the office to check.
 */

type Step = "details" | "questions" | "rate" | "done";

const COPY = {
  en: {
    title: "Tell us how we did",
    intro: "It takes about two minutes. Your answers help us care for every family better.",
    aboutYou: "About you",
    name: "Name",
    surname: "Surname",
    mobile: "Mobile number",
    mobileHint: "So we can follow up if you would like us to.",
    consent: "I agree that Induduzo Funeral Home may keep my answers and contact me about them.",
    start: "Start",
    next: "Next",
    back: "Back",
    send: "Send my answers",
    sending: "Sending…",
    of: (n: number, total: number) => `Question ${n} of ${total}`,
    yes: "Yes",
    no: "No",
    poor: "Poor",
    excellent: "Excellent",
    typeHere: "Type your answer here (optional)",
    thanks: (name: string) => `Thank you, ${name}.`,
    received: "Your answers have reached us.",
    rateAsk: "How would you rate our service?",
    stars: (n: number) => `${n} out of 5`,
    addMore: "Anything you would like to add? (optional)",
    sendRating: "Send rating",
    skip: "Skip",
    doneTitle: "Thank you for helping us care for families.",
    doneBody: "If you need us, day or night:",
    needName: "Please enter your name",
    needSurname: "Please enter your surname",
    needMobile: "Enter a valid South African mobile number, e.g. 082 123 4567",
    needConsent: "Please tick the box so we may keep your answers",
    needChoice: "Please choose an answer",
    needStars: "Please choose from 1 to 5 stars",
    loadFailed: "We could not open this page. Please check your connection and try again, or phone us on",
    tryAgain: "Try again",
  },
  zu: {
    title: "Sitshele ukuthi sikwenze kanjani",
    intro: "Kuthatha cishe imizuzu emibili. Izimpendulo zakho zisisiza ukuthi sinakekele yonke imindeni kangcono.",
    aboutYou: "Mayelana nawe",
    name: "Igama",
    surname: "Isibongo",
    mobile: "Inombolo yocingo",
    mobileHint: "Ukuze sikwazi ukukulandela uma ufisa.",
    consent: "Ngiyavuma ukuthi i-Induduzo Funeral Home ingagcina izimpendulo zami futhi ixhumane nami ngazo.",
    start: "Qala",
    next: "Okulandelayo",
    back: "Emuva",
    send: "Thumela izimpendulo zami",
    sending: "Iyathumela…",
    of: (n: number, total: number) => `Umbuzo ${n} kwangu-${total}`,
    yes: "Yebo",
    no: "Cha",
    poor: "Kubi",
    excellent: "Kuhle kakhulu",
    typeHere: "Bhala impendulo yakho lapha (akuphoqelekile)",
    thanks: (name: string) => `Siyabonga, ${name}.`,
    received: "Izimpendulo zakho sizitholile.",
    rateAsk: "Ungayilinganisa kanjani insizakalo yethu?",
    stars: (n: number) => `${n} kwangu-5`,
    addMore: "Ingabe kukhona ofuna ukukwengeza? (akuphoqelekile)",
    sendRating: "Thumela isilinganiso",
    skip: "Yeqa",
    doneTitle: "Siyabonga ngokusisiza ukunakekela imindeni.",
    doneBody: "Uma usidinga, emini noma ebusuku:",
    needName: "Sicela ufake igama lakho",
    needSurname: "Sicela ufake isibongo sakho",
    needMobile: "Faka inombolo yeselula yaseNingizimu Afrika evumelekile, isb. 082 123 4567",
    needConsent: "Sicela ukhethe ibhokisi ukuze sikwazi ukugcina izimpendulo zakho",
    needChoice: "Sicela ukhethe impendulo",
    needStars: "Sicela ukhethe kusuka ku-1 kuya ku-5",
    loadFailed: "Asikwazanga ukuvula leli khasi. Sicela uhlole uxhumano lwakho uzame futhi, noma usishayele ku-",
    tryAgain: "Zama futhi",
  },
} as const;

/** Keeps the page out of search results for as long as it is open. */
const useNoIndex = () => {
  useEffect(() => {
    const meta = document.createElement("meta");
    meta.name = "robots";
    meta.content = "noindex, nofollow";
    document.head.appendChild(meta);
    const title = document.title;
    document.title = "Induduzo Funeral Home";
    return () => {
      meta.remove();
      document.title = title;
    };
  }, []);
};

const questionText = (q: FeedbackQuestion, language: Language) =>
  (language === "zu" && q.text_zu) || q.text_en;

export default function Feedback({ code }: { code: string }) {
  useNoIndex();
  const { language: siteLanguage } = useLanguage();
  // Its own switch, without the site's reload: a reload here would lose answers.
  const [language, setLanguage] = useState<Language>(siteLanguage);
  const c = COPY[language];
  const source = useMemo<"qr" | "link">(
    () => (new URLSearchParams(window.location.search).get("via") === "qr" ? "qr" : "link"), []);

  const [questions, setQuestions] = useState<FeedbackQuestion[] | null>(null);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "missing" | "failed">("loading");
  const [attempt, setAttempt] = useState(0);

  const [step, setStep] = useState<Step>("details");
  const [index, setIndex] = useState(0);
  const [details, setDetails] = useState({ first_name: "", surname: "", mobile: "", consent: false, website: "" });
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [sendError, setSendError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [responseId, setResponseId] = useState<string | null>(null);
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetchQuestionnaire(code)
      .then(({ questions: qs }) => {
        if (cancelled) return;
        setQuestions(qs);
        setLoadState("ready");
      })
      .catch((error) => {
        if (cancelled) return;
        setLoadState(error instanceof SiteError && error.status === 404 ? "missing" : "failed");
      });
    return () => {
      cancelled = true;
    };
  }, [code, attempt]);

  if (loadState === "missing") return <NotFound />;

  const total = questions?.length ?? 0;
  const current = questions?.[index];

  const checkDetails = () => {
    const next: Record<string, string> = {};
    if (!details.first_name.trim()) next.first_name = c.needName;
    if (!details.surname.trim()) next.surname = c.needSurname;
    if (!isValidMobile(details.mobile)) next.mobile = c.needMobile;
    if (!details.consent) next.consent = c.needConsent;
    setErrors(next);
    return Object.keys(next).length === 0;
  };

  const checkCurrent = () => {
    if (!current || current.kind === "text" || answers[current.id]) {
      setErrors({});
      return true;
    }
    setErrors({ [current.id]: c.needChoice });
    return false;
  };

  const submitAnswers = async () => {
    if (!questions) return;
    setBusy(true);
    setSendError(null);
    try {
      const { id } = await sendFeedback(code, {
        first_name: details.first_name.trim(),
        surname: details.surname.trim(),
        mobile: normaliseMobile(details.mobile),
        answers: questions.map((q) => ({ id: q.id, answer: (answers[q.id] ?? "").trim() })),
        contact_consent: details.consent,
        source,
        language,
        website: details.website,
      });
      setResponseId(id);
      setStep("rate");
      window.scrollTo(0, 0);
    } catch (error) {
      if (error instanceof SiteError && Object.keys(error.fieldErrors).length) {
        // A detail or an answer the API refused: go back to where it is.
        const fields = error.fieldErrors;
        const answerKey = Object.keys(fields).find((k) => k.startsWith("answers."));
        if (answerKey) {
          const qIndex = questions.findIndex((q) => `answers.${q.id}` === answerKey);
          if (qIndex >= 0) {
            setIndex(qIndex);
            setErrors({ [questions[qIndex].id]: fields[answerKey] });
          }
        } else {
          setErrors(fields);
          setStep("details");
        }
      }
      setSendError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  const onNext = (event: FormEvent) => {
    event.preventDefault();
    if (step === "details") {
      if (checkDetails()) {
        setStep("questions");
        setIndex(0);
      }
      return;
    }
    if (!checkCurrent()) return;
    if (index < total - 1) setIndex(index + 1);
    else void submitAnswers();
  };

  const onRate = async (event: FormEvent) => {
    event.preventDefault();
    if (!rating) {
      setErrors({ rating: c.needStars });
      return;
    }
    if (!responseId) return;
    setBusy(true);
    setSendError(null);
    try {
      await sendRating(responseId, rating, comment);
      setStep("done");
    } catch (error) {
      setSendError(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-secondary/30">
      <main className="mx-auto flex min-h-screen w-full max-w-xl flex-col px-5 py-8">
        <div className="mb-6 flex items-start justify-between gap-4">
          <BrandLogo className="h-20" />
          <div className="flex gap-1 rounded-md border bg-background p-1 text-sm" role="group" aria-label="Language">
            {(["en", "zu"] as const).map((lang) => (
              <button
                key={lang}
                type="button"
                aria-pressed={language === lang}
                className={`rounded px-3 py-1.5 font-medium ${
                  language === lang ? "bg-primary text-primary-foreground" : "text-foreground"
                }`}
                onClick={() => setLanguage(lang)}
              >
                {lang === "en" ? "English" : "isiZulu"}
              </button>
            ))}
          </div>
        </div>

        <div className="rounded-lg border bg-background p-6 shadow-sm sm:p-8">
          {loadState === "loading" && (
            <div aria-busy="true" className="space-y-3">
              <div className="h-7 w-3/4 animate-pulse rounded bg-secondary" />
              <div className="h-4 w-full animate-pulse rounded bg-secondary" />
              <div className="h-4 w-5/6 animate-pulse rounded bg-secondary" />
            </div>
          )}

          {loadState === "failed" && (
            <div role="alert" className="space-y-4">
              <p>
                {c.loadFailed}{" "}
                <a href={TWENTY_FOUR_HOUR_LINE.link} className="font-semibold text-primary underline">
                  {TWENTY_FOUR_HOUR_LINE.display}
                </a>
                .
              </p>
              <Button onClick={() => {
                setLoadState("loading");
                setAttempt((n) => n + 1);
              }}>{c.tryAgain}</Button>
            </div>
          )}

          {loadState === "ready" && step === "details" && (
            <form onSubmit={onNext} noValidate className="space-y-5">
              <div>
                <h1 className="mb-2 text-2xl font-semibold sm:text-3xl">{c.title}</h1>
                <p className="text-muted-foreground">{c.intro}</p>
              </div>
              <h2 className="text-lg font-semibold">{c.aboutYou}</h2>

              {/* Honeypot: hidden from people, filled by bots. */}
              <div className="absolute -left-[9999px] h-px w-px overflow-hidden" aria-hidden="true">
                <label htmlFor="fb-website">Website</label>
                <input id="fb-website" name="website" type="text" tabIndex={-1} autoComplete="off"
                  value={details.website}
                  onChange={(e) => setDetails({ ...details, website: e.target.value })} />
              </div>

              <Field label={c.name} required error={errors.first_name}>
                {(props) => (
                  <Input {...props} autoComplete="given-name" autoCapitalize="words" maxLength={80}
                    value={details.first_name}
                    onChange={(e) => setDetails({ ...details, first_name: e.target.value })} />
                )}
              </Field>
              <Field label={c.surname} required error={errors.surname}>
                {(props) => (
                  <Input {...props} autoComplete="family-name" autoCapitalize="words" maxLength={80}
                    value={details.surname}
                    onChange={(e) => setDetails({ ...details, surname: e.target.value })} />
                )}
              </Field>
              <Field label={c.mobile} required error={errors.mobile} hint={c.mobileHint}>
                {(props) => (
                  <Input {...props} type="tel" inputMode="tel" autoComplete="tel" placeholder="082 123 4567"
                    value={details.mobile}
                    onChange={(e) => setDetails({ ...details, mobile: e.target.value })} />
                )}
              </Field>

              <div className="space-y-2">
                <div className="flex items-start gap-3">
                  <Checkbox id="fb-consent" checked={details.consent} className="mt-1"
                    aria-invalid={Boolean(errors.consent)}
                    aria-describedby={errors.consent ? "fb-consent-error" : undefined}
                    onCheckedChange={(v) => setDetails({ ...details, consent: v === true })} />
                  <label htmlFor="fb-consent" className="text-sm leading-relaxed">
                    {c.consent}
                    <span className="ml-1 text-primary" aria-hidden="true">*</span>
                  </label>
                </div>
                {errors.consent && (
                  <p id="fb-consent-error" role="alert" className="text-sm font-medium text-destructive">
                    {errors.consent}
                  </p>
                )}
              </div>

              {sendError && <p role="alert" className="text-sm font-medium text-destructive">{sendError}</p>}
              <Button type="submit" size="lg" className="w-full">{c.start}</Button>
            </form>
          )}

          {loadState === "ready" && step === "questions" && current && (
            <form onSubmit={onNext} noValidate className="space-y-6">
              <div>
                <p className="mb-2 text-sm font-medium text-muted-foreground">{c.of(index + 1, total)}</p>
                <div className="h-1.5 w-full overflow-hidden rounded bg-secondary" aria-hidden="true">
                  <div className="h-full bg-primary transition-all" style={{ width: `${((index + 1) / total) * 100}%` }} />
                </div>
              </div>

              <fieldset className="space-y-4">
                <legend className="text-xl font-semibold leading-snug">{questionText(current, language)}</legend>
                {current.kind === "text" && (
                  <Textarea rows={4} maxLength={1000} placeholder={c.typeHere}
                    aria-label={questionText(current, language)}
                    value={answers[current.id] ?? ""}
                    onChange={(e) => setAnswers({ ...answers, [current.id]: e.target.value })} />
                )}
                {current.kind === "yes_no" && (
                  <div className="grid grid-cols-2 gap-3">
                    {(["yes", "no"] as const).map((value) => (
                      <Choice key={value} name={current.id} value={value}
                        label={value === "yes" ? c.yes : c.no}
                        checked={answers[current.id] === value}
                        onChange={() => setAnswers({ ...answers, [current.id]: value })} />
                    ))}
                  </div>
                )}
                {current.kind === "scale" && (
                  <div>
                    <div className="grid grid-cols-5 gap-2">
                      {["1", "2", "3", "4", "5"].map((value) => (
                        <Choice key={value} name={current.id} value={value} label={value}
                          checked={answers[current.id] === value}
                          onChange={() => setAnswers({ ...answers, [current.id]: value })} />
                      ))}
                    </div>
                    <div className="mt-2 flex justify-between text-sm text-muted-foreground" aria-hidden="true">
                      <span>{c.poor}</span>
                      <span>{c.excellent}</span>
                    </div>
                  </div>
                )}
                {errors[current.id] && (
                  <p role="alert" className="text-sm font-medium text-destructive">{errors[current.id]}</p>
                )}
              </fieldset>

              {sendError && <p role="alert" className="text-sm font-medium text-destructive">{sendError}</p>}
              <div className="flex gap-3">
                <Button type="button" variant="outline" size="lg" disabled={busy}
                  onClick={() => {
                    setErrors({});
                    if (index === 0) setStep("details");
                    else setIndex(index - 1);
                  }}>
                  {c.back}
                </Button>
                <Button type="submit" size="lg" className="flex-1" disabled={busy}>
                  {busy ? c.sending : index < total - 1 ? c.next : c.send}
                </Button>
              </div>
            </form>
          )}

          {step === "rate" && (
            <form onSubmit={onRate} noValidate className="space-y-6">
              <div>
                <h1 className="mb-2 text-2xl font-semibold sm:text-3xl">{c.thanks(details.first_name.trim())}</h1>
                <p className="text-muted-foreground">{c.received}</p>
              </div>
              <fieldset>
                <legend className="mb-3 text-xl font-semibold">{c.rateAsk}</legend>
                <div className="flex gap-2" role="radiogroup" aria-label={c.rateAsk}>
                  {[1, 2, 3, 4, 5].map((n) => (
                    <button key={n} type="button" role="radio" aria-checked={rating === n}
                      aria-label={c.stars(n)}
                      className="rounded-md p-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      onClick={() => {
                        setRating(n);
                        setErrors({});
                      }}>
                      <Star className={`h-10 w-10 ${n <= rating ? "fill-primary text-primary" : "text-muted-foreground"}`} />
                    </button>
                  ))}
                </div>
                {errors.rating && <p role="alert" className="mt-2 text-sm font-medium text-destructive">{errors.rating}</p>}
              </fieldset>
              <div>
                <label htmlFor="fb-comment" className="mb-1.5 block text-sm font-medium">{c.addMore}</label>
                <Textarea id="fb-comment" rows={3} maxLength={1000} value={comment}
                  onChange={(e) => setComment(e.target.value)} />
              </div>
              {sendError && <p role="alert" className="text-sm font-medium text-destructive">{sendError}</p>}
              <div className="flex gap-3">
                <Button type="button" variant="outline" size="lg" disabled={busy} onClick={() => setStep("done")}>
                  {c.skip}
                </Button>
                <Button type="submit" size="lg" className="flex-1" disabled={busy}>
                  {busy ? c.sending : c.sendRating}
                </Button>
              </div>
            </form>
          )}

          {step === "done" && (
            <div className="space-y-4 text-center">
              <h1 className="text-2xl font-semibold sm:text-3xl">{c.doneTitle}</h1>
              <p className="text-muted-foreground">{c.doneBody}</p>
              <a href={TWENTY_FOUR_HOUR_LINE.link} className="block text-xl font-semibold text-primary">
                {TWENTY_FOUR_HOUR_LINE.display}
              </a>
            </div>
          )}
        </div>

        <p className="mt-6 text-center text-sm italic text-muted-foreground">“Siyazazi Izingxaki Zakho”</p>
      </main>
    </div>
  );
}

/** A large, tappable radio: the whole box is the target, not a small dot. */
function Choice({ name, value, label, checked, onChange }: {
  name: string;
  value: string;
  label: string;
  checked: boolean;
  onChange: () => void;
}) {
  return (
    <label
      className={`flex cursor-pointer items-center justify-center rounded-md border-2 px-3 py-4 text-lg font-semibold transition-colors focus-within:ring-2 focus-within:ring-ring ${
        checked ? "border-primary bg-primary/10 text-primary" : "border-input bg-background hover:border-primary/50"
      }`}
    >
      <input type="radio" name={name} value={value} checked={checked} onChange={onChange} className="sr-only" />
      {label}
    </label>
  );
}
