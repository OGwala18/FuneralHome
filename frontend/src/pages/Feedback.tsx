import { useEffect, useMemo, useRef, useState, type FormEvent, type Ref } from "react";

import { BrandLogo } from "@/components/BrandLogo";
import { Field } from "@/components/form/Field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { TWENTY_FOUR_HOUR_LINE, WHATSAPP_LINE, WHATSAPP_URL } from "@/lib/contact";
import { useLanguage, type Language } from "@/lib/i18n";
import { isValidMobile, normaliseMobile } from "@/lib/registration";
import {
  fetchQuestionnaire,
  sendFeedback,
  SiteError,
  type FeedbackAnswer,
  type FeedbackChoice,
  type FeedbackQuestion,
  type Questionnaire,
} from "@/lib/site";
import NotFound from "./NotFound";

/**
 * The owner's post-funeral survey, at /feedback/<code> (and ?v=short for the
 * five-question version).
 *
 * Not linked from anywhere on the site, not in the sitemap, disallowed in
 * robots.txt and marked noindex. It opens only from its own link, which the
 * office sends with its WhatsApp condolence message or prints as a QR code
 * (Settings > Website settings in the portal). A wrong or retired code shows
 * the site's ordinary 404.
 *
 * The introduction, then the questions one at a time (kinder on a phone, after
 * a loss), then an optional name and number, then thanks. Answering is
 * voluntary: Next always works unless staff marked a question as required.
 *
 * The wording of the questions comes from the API (staff edit it). The page's
 * own words below are the owner's draft, English and isiZulu.
 */

type Step = "intro" | "question" | "contact" | "done";

const COPY = {
  en: {
    start: "Start",
    next: "Next",
    skip: "Skip",
    back: "Back",
    of: (n: number, total: number) => `Question ${n} of ${total}`,
    typeHere: "Type your answer here",
    contactTitle: "Would you like us to contact you? (optional)",
    contactBody: "Leave blank to stay anonymous. By giving your details you agree that Induduzo may contact you about your feedback.",
    name: "Your name",
    mobile: "Your cellphone number",
    send: "Send",
    sending: "Sending…",
    thanksTitle: "Thank you. Siyabonga.",
    thanksBody: "If you need assistance, call our 24-hour line on",
    orWhatsApp: "or WhatsApp",
    needAnswer: "Please answer this question",
    needAll: "Please choose one answer for each line",
    needMobile: "Enter a valid South African cellphone number, e.g. 082 123 4567",
    needSomething: "Please answer at least one question before sending.",
    loadFailed: "We could not open this page. Please check your connection and try again, or phone us on",
    tryAgain: "Try again",
    language: "Language",
    optional: "Optional",
    requiredSr: "(required)",
    stale: "These questions have just been changed. Please reload the page to see the latest ones; your answers so far are kept.",
    reload: "Reload the page",
    sendFailed: "We could not send your answers just now. Please try again, or phone us on",
    invalidAnswer: null as string | null,   // English shows the server's own words
    invalidName: null as string | null,
  },
  zu: {
    start: "Qala",
    next: "Okulandelayo",
    skip: "Yeqa",
    back: "Emuva",
    of: (n: number, total: number) => `Umbuzo ${n} kwangu-${total}`,
    typeHere: "Bhala impendulo yakho lapha",
    contactTitle: "Ungathanda ukuthi sikuthinte? (akuphoqelekile)",
    contactBody: "Shiya kungenalutho uma ufuna ukungaziwa. Ngokunikeza imininingwane yakho uyavuma ukuthi i-Induduzo ingakuthinta mayelana nombono wakho.",
    name: "Igama lakho",
    mobile: "Inombolo yakho kamakhalekhukhwini",
    send: "Thumela",
    sending: "Iyathumela…",
    thanksTitle: "Siyabonga.",
    thanksBody: "Uma udinga usizo, shayela inombolo yethu esebenza amahora angu-24 ethi",
    orWhatsApp: "noma usithumelele i-WhatsApp ku-",
    needAnswer: "Sicela uphendule lo mbuzo",
    needAll: "Sicela ukhethe impendulo eyodwa emugqeni ngamunye",
    needMobile: "Faka inombolo kamakhalekhukhwini yaseNingizimu Afrika evumelekile, isb. 082 123 4567",
    needSomething: "Sicela uphendule okungenani umbuzo owodwa ngaphambi kokuthumela.",
    loadFailed: "Asikwazanga ukuvula leli khasi. Sicela uhlole uxhumano lwakho uzame futhi, noma usishayele ku-",
    tryAgain: "Zama futhi",
    language: "Ulimi",
    optional: "Akuphoqelekile",
    requiredSr: "(kuyaphoqeleka)",
    stale: "Le mibuzo isanda kushintshwa. Sicela ulayishe kabusha ikhasi ukuze ubone emisha; izimpendulo zakho ezikhona zigciniwe.",
    reload: "Layisha kabusha ikhasi",
    sendFailed: "Asikwazanga ukuthumela izimpendulo zakho manje. Sicela uzame futhi, noma usishayele ku-",
    invalidAnswer: "Sicela uhlole impendulo yakho kulo mbuzo." as string | null,
    invalidName: "Sicela usebenzise izinhlamvu egameni lakho." as string | null,
  },
};

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

/** The answers given so far, kept in this tab so a reload (or a changed
 *  questionnaire) does not lose them. Answers only: never the name or number. */
const draftKey = (code: string, version: string) => `induduzo-feedback-${code}-${version}`;

const readDraft = (code: string, version: string): Record<string, FeedbackAnswer> => {
  try {
    const raw = sessionStorage.getItem(draftKey(code, version));
    return raw ? (JSON.parse(raw) as Record<string, FeedbackAnswer>) : {};
  } catch {
    return {};
  }
};

const pick = (en: string | null, zu: string | null, language: Language) =>
  (language === "zu" && zu) || en || "";

const label = (choice: FeedbackChoice, language: Language) => pick(choice.en, choice.zu, language);

const isAnswered = (q: FeedbackQuestion, answer: FeedbackAnswer | undefined) => {
  if (answer === undefined || answer === "") return false;
  if (q.kind === "grid") return typeof answer === "object" && Object.keys(answer).length > 0;
  if (q.kind === "text") return typeof answer === "string" && answer.trim() !== "";
  return true;
};

export default function Feedback({ code }: { code: string }) {
  useNoIndex();
  const { language: siteLanguage } = useLanguage();
  // Its own switch, without the site's reload: a reload here would lose answers.
  const [language, setLanguage] = useState<Language>(siteLanguage);
  const c = COPY[language];
  const params = useMemo(() => new URLSearchParams(window.location.search), []);
  const source: "qr" | "link" = params.get("via") === "qr" ? "qr" : "link";
  const version: "full" | "short" = params.get("v") === "short" ? "short" : "full";

  const [survey, setSurvey] = useState<Questionnaire | null>(null);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "missing" | "failed">("loading");
  const [attempt, setAttempt] = useState(0);

  const [step, setStep] = useState<Step>("intro");
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, FeedbackAnswer>>(() => readDraft(code, version));
  const [contact, setContact] = useState({ name: "", mobile: "", website: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [sendError, setSendError] = useState<string | null>(null);
  // The API refused an answer to a question this page no longer has.
  const [stale, setStale] = useState(false);
  const [busy, setBusy] = useState(false);
  // Where focus goes when the step or question changes, so a screen reader
  // hears the new question rather than staying on the button just pressed.
  const headingRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    try {
      if (step === "done") sessionStorage.removeItem(draftKey(code, version));
      else sessionStorage.setItem(draftKey(code, version), JSON.stringify(answers));
    } catch {
      /* private browsing: answers are simply not kept across a reload */
    }
  }, [answers, step, code, version]);

  // The document's language follows this page's switch, so screen readers
  // pronounce isiZulu as isiZulu. Put back on the way out.
  useEffect(() => {
    const previous = document.documentElement.lang;
    document.documentElement.lang = language;
    return () => {
      document.documentElement.lang = previous;
    };
  }, [language]);

  useEffect(() => {
    if (step !== "intro" || index !== 0) headingRef.current?.focus();
  }, [step, index]);

  useEffect(() => {
    let cancelled = false;
    fetchQuestionnaire(code, version)
      .then((next) => {
        if (cancelled) return;
        setSurvey(next);
        setLoadState("ready");
      })
      .catch((error) => {
        if (cancelled) return;
        setLoadState(error instanceof SiteError && error.status === 404 ? "missing" : "failed");
      });
    return () => {
      cancelled = true;
    };
  }, [code, version, attempt]);

  if (loadState === "missing") return <NotFound />;

  const questions = survey?.questions ?? [];
  const total = questions.length;
  const current = questions[index];

  const go = (next: Step, at = index) => {
    setErrors({});
    setSendError(null);
    setStep(next);
    setIndex(at);
    window.scrollTo(0, 0);
  };

  const setAnswer = (id: string, value: FeedbackAnswer) => {
    setAnswers((all) => ({ ...all, [id]: value }));
    setErrors({});
  };

  const checkCurrent = () => {
    if (!current || !current.required) return true;
    const answer = answers[current.id];
    if (!isAnswered(current, answer)) {
      setErrors({ [current.id]: c.needAnswer });
      return false;
    }
    if (current.kind === "grid" && Object.keys(answer as Record<string, string>).length
        < (current.rows?.length ?? 0)) {
      setErrors({ [current.id]: c.needAll });
      return false;
    }
    return true;
  };

  const onNext = (event: FormEvent) => {
    event.preventDefault();
    if (!checkCurrent()) return;
    if (index < total - 1) go("question", index + 1);
    else go("contact");
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const answered = questions.filter((q) => isAnswered(q, answers[q.id]));
    if (answered.length === 0) {
      setSendError(c.needSomething);
      return;
    }
    if (contact.mobile.trim() && !isValidMobile(contact.mobile)) {
      setErrors({ mobile: c.needMobile });
      return;
    }
    setBusy(true);
    setSendError(null);
    try {
      await sendFeedback(code, {
        answers: answered.map((q) => {
          const value = answers[q.id];
          return { id: q.id, answer: typeof value === "string" ? value.trim() : value };
        }),
        name: contact.name.trim() || null,
        mobile: contact.mobile.trim() ? normaliseMobile(contact.mobile) : null,
        version,
        source,
        language,
        website: contact.website,
      });
      go("done");
    } catch (error) {
      const fields = error instanceof SiteError ? error.fieldErrors : {};
      const answerKeys = Object.keys(fields).filter((k) => k.startsWith("answers."));
      // The first refused answer to a question on this page: go back to it.
      const qIndex = questions.findIndex((q) => answerKeys.includes(`answers.${q.id}`));
      if (answerKeys.some((k) => !questions.some((q) => `answers.${q.id}` === k))) {
        // Staff changed the questions while this family was answering.
        setStale(true);
      } else if (qIndex >= 0) {
        const q = questions[qIndex];
        go("question", qIndex);
        setErrors({ [q.id]: c.invalidAnswer ?? fields[`answers.${q.id}`] });
        return;
      } else if (fields.mobile || fields.name) {
        setErrors({
          ...(fields.mobile ? { mobile: c.needMobile } : {}),
          ...(fields.name ? { name: c.invalidName ?? fields.name } : {}),
        });
        return;
      } else if (language === "zu" || !(error instanceof SiteError) || error.status === 0) {
        setSendError(`${c.sendFailed} ${TWENTY_FOUR_HOUR_LINE.display}.`);
        return;
      }
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
          <div className="flex gap-1 rounded-md border bg-background p-1 text-sm" role="group"
            aria-label={c.language}>
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

          {loadState === "ready" && survey && step === "intro" && (
            <div className="space-y-6">
              <h1 className="text-2xl font-semibold sm:text-3xl">
                {pick(survey.title_en, survey.title_zu, language)}
              </h1>
              <p className="whitespace-pre-line leading-relaxed text-muted-foreground">
                {pick(survey.intro_en, survey.intro_zu, language)}
              </p>
              <Button size="lg" className="w-full" onClick={() => go("question", 0)}>{c.start}</Button>
            </div>
          )}

          {stale && step !== "done" && (
            <div role="alert" className="mb-6 space-y-3 rounded-md border border-destructive/40 bg-destructive/5 p-4">
              <p className="text-sm font-medium">{c.stale}</p>
              <Button type="button" size="sm" onClick={() => window.location.reload()}>{c.reload}</Button>
            </div>
          )}

          {loadState === "ready" && step === "question" && current && (
            <form onSubmit={onNext} noValidate className="space-y-6">
              <div>
                <p className="mb-2 text-sm font-medium text-muted-foreground">{c.of(index + 1, total)}</p>
                <div className="h-1.5 w-full overflow-hidden rounded bg-secondary" aria-hidden="true">
                  <div className="h-full bg-primary" style={{ width: `${((index + 1) / total) * 100}%` }} />
                </div>
              </div>

              <QuestionField
                headingRef={headingRef}
                requiredSr={c.requiredSr}
                question={current}
                language={language}
                answer={answers[current.id]}
                error={errors[current.id]}
                placeholder={c.typeHere}
                onChange={(value) => setAnswer(current.id, value)}
              />

              <div className="flex gap-3">
                <Button type="button" variant="outline" size="lg"
                  onClick={() => (index === 0 ? go("intro", 0) : go("question", index - 1))}>
                  {c.back}
                </Button>
                <Button type="submit" size="lg" className="flex-1">
                  {isAnswered(current, answers[current.id]) || current.required ? c.next : c.skip}
                </Button>
              </div>
            </form>
          )}

          {loadState === "ready" && step === "contact" && (
            <form onSubmit={submit} noValidate className="space-y-5">
              <div>
                <h2 ref={headingRef as Ref<HTMLHeadingElement>} tabIndex={-1}
                  className="mb-2 text-xl font-semibold focus:outline-none">{c.contactTitle}</h2>
                <p className="text-sm leading-relaxed text-muted-foreground">{c.contactBody}</p>
              </div>

              {/* Honeypot: hidden from people, filled by bots. */}
              <div className="absolute -left-[9999px] h-px w-px overflow-hidden" aria-hidden="true">
                <label htmlFor="fb-website">Website</label>
                <input id="fb-website" name="website" type="text" tabIndex={-1} autoComplete="off"
                  value={contact.website}
                  onChange={(e) => setContact({ ...contact, website: e.target.value })} />
              </div>

              <Field label={c.name} error={errors.name} optionalLabel={c.optional}>
                {(props) => (
                  <Input {...props} autoComplete="name" autoCapitalize="words" maxLength={120}
                    value={contact.name}
                    onChange={(e) => setContact({ ...contact, name: e.target.value })} />
                )}
              </Field>
              <Field label={c.mobile} error={errors.mobile} optionalLabel={c.optional}>
                {(props) => (
                  <Input {...props} type="tel" inputMode="tel" autoComplete="tel" placeholder="082 123 4567"
                    value={contact.mobile}
                    onChange={(e) => setContact({ ...contact, mobile: e.target.value })} />
                )}
              </Field>

              {sendError && <p role="alert" className="text-sm font-medium text-destructive">{sendError}</p>}
              <div className="flex gap-3">
                <Button type="button" variant="outline" size="lg" disabled={busy}
                  onClick={() => go("question", total - 1)}>
                  {c.back}
                </Button>
                <Button type="submit" size="lg" className="flex-1" disabled={busy}>
                  {busy ? c.sending : c.send}
                </Button>
              </div>
            </form>
          )}

          {step === "done" && (
            <div className="space-y-4 text-center">
              <h1 ref={headingRef as Ref<HTMLHeadingElement>} tabIndex={-1}
                className="text-2xl font-semibold focus:outline-none sm:text-3xl">{c.thanksTitle}</h1>
              <p className="leading-relaxed text-muted-foreground">
                {c.thanksBody}{" "}
                <a href={TWENTY_FOUR_HOUR_LINE.link} className="font-semibold text-primary">
                  {TWENTY_FOUR_HOUR_LINE.display}
                </a>{" "}
                {c.orWhatsApp}{language === "zu" ? "" : " "}
                <a href={WHATSAPP_URL} target="_blank" rel="noopener noreferrer" className="font-semibold text-primary">
                  {WHATSAPP_LINE.display}
                </a>
                .
              </p>
            </div>
          )}
        </div>

        <p className="mt-6 text-center text-sm italic text-muted-foreground">“Siyazazi Izingxaki Zakho”</p>
      </main>
    </div>
  );
}

/** One question, drawn for its kind. */
function QuestionField({ question: q, language, answer, error, placeholder, onChange, headingRef,
  requiredSr }: {
  headingRef: Ref<HTMLElement>;
  requiredSr: string;
  question: FeedbackQuestion;
  language: Language;
  answer: FeedbackAnswer | undefined;
  error?: string;
  placeholder: string;
  onChange: (value: FeedbackAnswer) => void;
}) {
  const text = pick(q.text_en, q.text_zu, language);
  const low = pick(q.low_en, q.low_zu, language);
  const high = pick(q.high_en, q.high_zu, language);
  const hintId = `${q.id}-scale-words`;
  const hasHint = q.kind === "scale" && Boolean(low || high);
  return (
    <fieldset className="space-y-4" aria-describedby={hasHint ? hintId : undefined}>
      <legend ref={headingRef as Ref<HTMLLegendElement>} tabIndex={-1}
        className="text-xl font-semibold leading-snug focus:outline-none">
        {text}
        {q.required && (
          <>
            <span className="ml-1 text-primary" aria-hidden="true">*</span>
            <span className="sr-only"> {requiredSr}</span>
          </>
        )}
      </legend>

      {q.kind === "choice" && (
        <div className="grid gap-2">
          {(q.options ?? []).map((option) => (
            <Choice key={option.value} name={q.id} label={label(option, language)}
              checked={answer === option.value} onChange={() => onChange(option.value)} align="start" />
          ))}
        </div>
      )}

      {q.kind === "scale" && q.min !== null && q.max !== null && (
        <div>
          <div className={`grid gap-2 ${q.max - q.min > 5 ? "grid-cols-6" : "grid-cols-5"}`}>
            {Array.from({ length: q.max - q.min + 1 }, (_, i) => q.min! + i).map((n) => (
              <Choice key={n} name={q.id} label={String(n)} checked={answer === n}
                onChange={() => onChange(n)} />
            ))}
          </div>
          {hasHint && (
            <p id={hintId} className="mt-2 text-sm text-muted-foreground">
              {[low && `${q.min} = ${low}`, high && `${q.max} = ${high}`].filter(Boolean).join(" · ")}
            </p>
          )}
        </div>
      )}

      {q.kind === "grid" && (
        <div className="space-y-5">
          {(q.rows ?? []).map((row) => {
            const chosen = (answer && typeof answer === "object") ? answer : {};
            return (
              <div key={row.value} role="radiogroup" aria-label={label(row, language)} className="space-y-2">
                <p className="font-medium">{label(row, language)}</p>
                <div className="flex flex-wrap gap-2">
                  {(q.options ?? []).map((option) => (
                    <Choice key={option.value} name={`${q.id}-${row.value}`} small
                      label={label(option, language)} checked={chosen[row.value] === option.value}
                      onChange={() => onChange({ ...chosen, [row.value]: option.value })} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {q.kind === "text" && (
        <Textarea rows={5} maxLength={2000} placeholder={placeholder} aria-label={text}
          value={typeof answer === "string" ? answer : ""}
          onChange={(e) => onChange(e.target.value)} />
      )}

      {error && <p role="alert" className="text-sm font-medium text-destructive">{error}</p>}
    </fieldset>
  );
}

/** A large, tappable radio: the whole box is the target, not a small dot. */
function Choice({ name, label, checked, onChange, align = "center", small = false }: {
  name: string;
  label: string;
  checked: boolean;
  onChange: () => void;
  align?: "center" | "start";
  small?: boolean;
}) {
  return (
    <label
      className={`flex cursor-pointer items-center rounded-md border-2 transition-colors focus-within:ring-2 focus-within:ring-ring ${
        align === "start" ? "justify-start text-left" : "justify-center"
      } ${small ? "px-3 py-2 text-sm font-medium" : "min-h-12 px-3 py-3 text-base font-semibold"} ${
        checked ? "border-primary bg-primary/10 text-primary" : "border-input bg-background hover:border-primary/50"
      }`}
    >
      <input type="radio" name={name} checked={checked} onChange={onChange} className="sr-only" />
      {label}
    </label>
  );
}
