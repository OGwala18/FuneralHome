import { Fragment, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  fetchFeedback,
  replaceFeedbackLink,
  updateFeedbackSurvey,
  type FeedbackOverview,
  type FeedbackQuestion,
  type FeedbackQuestionResult,
  type FeedbackSurvey,
} from "@/lib/api";
import { formatDate } from "@/lib/derive";
import { qrCanvas } from "@/lib/qr";
import { Badge, Button, Empty, Field, Notice, Skeleton } from "@/components/ui";
import FeedbackQuestionEditor, { MAX_QUESTIONS, newQuestion, problemsIn } from "./FeedbackQuestionEditor";

/**
 * The owner's post-funeral survey: "Post-Funeral Family Feedback".
 *
 * It is not on the website: it opens only from its own link, which the office
 * sends with the WhatsApp condolence message below or prints as a QR code. Two
 * versions share one link: the full ten questions, and the five-question short
 * version (?v=short) made of the questions marked "In the short version". The
 * QR code adds ?via=qr, so the results show which way families came.
 *
 * "Make a new link" retires the old one at once: every printed QR code and
 * every link already sent stops working. That is the point when a link has
 * spread too far, and the reason the button asks first.
 */

// The owner's WhatsApp message to send with the link (survey draft, 26 Nov 2026).
const MESSAGE = {
  en: (name: string, link: string) =>
    `Dear ${name}, Induduzo Funeral Home extends our condolences once again. When you are ready, please share how we served your family: ${link}. Siyabonga.`,
  zu: (name: string, link: string) =>
    `Sawubona ${name}, i-Induduzo Funeral Home iphinda idlulisa amazwi enduduzo. Uma usukulungele, sicela usitshele ukuthi siwusize kanjani umndeni wakho: ${link}. Siyabonga.`,
};

type Version = "full" | "short";

export default function FeedbackSettings() {
  const [data, setData] = useState<FeedbackOverview | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [questions, setQuestions] = useState<FeedbackQuestion[]>([]);
  const [wording, setWording] = useState({ title_en: "", title_zu: "", intro_en: "", intro_zu: "" });
  const [dirty, setDirty] = useState(false);
  const [editorKey, setEditorKey] = useState(0);
  const [busy, setBusy] = useState<"" | "save" | "open" | "link">("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [confirmNewLink, setConfirmNewLink] = useState(false);
  const [openRow, setOpenRow] = useState<string | null>(null);
  const [version, setVersion] = useState<Version>("full");
  const [messageLanguage, setMessageLanguage] = useState<"en" | "zu">("en");
  const [familyName, setFamilyName] = useState("");

  const reset = (next: FeedbackOverview) => {
    setData(next);
    setQuestions(next.survey.questions);
    setWording({
      title_en: next.survey.title_en, title_zu: next.survey.title_zu ?? "",
      intro_en: next.survey.intro_en, intro_zu: next.survey.intro_zu ?? "",
    });
    setDirty(false);
    setEditorKey((k) => k + 1);
  };

  const load = () => {
    setLoadError(null);
    fetchFeedback().then(reset).catch((e) => setLoadError(e instanceof Error ? e.message : String(e)));
  };
  useEffect(load, []);

  const link = data ? (version === "short" ? data.survey.short_link : data.survey.link) : "";
  const qrLink = link ? `${link}${link.includes("?") ? "&" : "?"}via=qr` : "";
  const qrImage = useMemo(() => (qrLink ? qrCanvas(qrLink, 600).toDataURL("image/png") : ""), [qrLink]);

  if (loadError) {
    return (
      <Notice tone="error" title="Could not load the questionnaire." detail={loadError}
        action={<Button small onClick={load}>Try again</Button>} />
    );
  }
  if (!data) return <section className="card"><Skeleton rows={6} /></section>;

  const { survey, summary, responses, can_edit: canEdit } = data;
  const shortCount = survey.questions.filter((q) => q.short).length;
  const message = MESSAGE[messageLanguage](
    familyName.trim() || (messageLanguage === "zu" ? "[Igama]" : "[Name]"), link);

  /** `keepEdits`: the action changes only the link or open/closed state, so
   *  any unsaved wording and question edits on the page are left alone. */
  const run = async (what: typeof busy, action: () => Promise<FeedbackSurvey>, done: string,
                     keepEdits = false) => {
    setBusy(what);
    setError(null);
    setSaved(null);
    try {
      const survey = await action();
      setSaved(done);
      if (keepEdits) {
        setData((d) => d && {
          ...d,
          survey: { ...d.survey, is_open: survey.is_open, link_code: survey.link_code,
            link: survey.link, short_link: survey.short_link },
        });
      } else {
        fetchFeedback().then(reset).catch(() => undefined);
      }
    } catch (e) {
      const fields = e instanceof ApiError ? Object.values(e.fieldErrors) : [];
      setError([e instanceof Error ? e.message : String(e), ...fields].join(" "));
    } finally {
      setBusy("");
    }
  };

  const copy = async (text: string, what: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(what);
      window.setTimeout(() => setCopied(null), 2500);
    } catch {
      setError("Could not copy. Select the text and copy it by hand.");
    }
  };

  const downloadQr = () => {
    const a = document.createElement("a");
    a.href = qrCanvas(qrLink, 1200).toDataURL("image/png");
    a.download = `induduzo-feedback-${version}-qr.png`;
    a.click();
  };

  const save = () => {
    const problems = problemsIn(questions);
    if (!wording.title_en.trim()) problems.unshift("Give the questionnaire an English title.");
    if (!wording.intro_en.trim()) problems.unshift("Give the questionnaire an English introduction.");
    if (problems.length) {
      setSaved(null);
      setError(problems.join(" "));
      return Promise.resolve();
    }
    return run("save", () => updateFeedbackSurvey({
    title_en: wording.title_en.trim(),
    title_zu: wording.title_zu.trim() || null,
    intro_en: wording.intro_en.trim(),
    intro_zu: wording.intro_zu.trim() || null,
    questions: questions.map((q) => ({
      ...q,
      text_en: q.text_en.trim(),
      text_zu: q.text_zu?.trim() || null,
    })),
  }), "Saved. The questionnaire asks this from now on.");
  };

  return (
    <section className="card stack" aria-labelledby="feedback-title">
      <div className="stack-8">
        <h2 className="t-title" id="feedback-title">Family feedback questionnaire</h2>
        <p className="t-small muted">
          A private page on the website. It is not in the menu and search engines are told to
          skip it: families reach it only through this link or its QR code.
        </p>
      </div>

      {saved && <Notice tone="success" title={saved} />}
      {error && <Notice tone="error" title="Not saved" detail={error} />}

      {/* The link, its QR code, and the WhatsApp message to send with it */}
      <div className="settings-sections" role="tablist" aria-label="Version">
        {([["full", `Full (${survey.questions.length} questions)`],
          ["short", `Short (${shortCount || survey.questions.length} questions)`]] as [Version, string][])
          .map(([id, text]) => (
            <button key={id} type="button" role="tab" aria-selected={version === id}
              className={`btn btn-small${version === id ? " btn-selected" : ""}`}
              onClick={() => setVersion(id)}>
              {text}
            </button>
          ))}
      </div>

      <div className="feedback-link">
        <div className="stack grow">
          <div className="row">
            <Badge tone={survey.is_open ? "success" : "neutral"}>{survey.is_open ? "Open" : "Closed"}</Badge>
            <span className="t-small muted">
              {survey.is_open ? "Anyone with the link can answer."
                : "The link shows “page not found” until it is opened again."}
            </span>
          </div>
          <code className="feedback-url">{link}</code>
          <div className="row">
            <Button small onClick={() => void copy(link, "link")}>{copied === "link" ? "Copied" : "Copy link"}</Button>
            <Button small onClick={downloadQr}>Download QR code</Button>
            <a className="btn btn-small btn-ghost" href={link} target="_blank" rel="noopener noreferrer">
              Open the page
            </a>
          </div>
          {canEdit && (
            <div className="row">
              <Button small variant={survey.is_open ? "secondary" : "primary"} loading={busy === "open"}
                onClick={() => void run("open", () => updateFeedbackSurvey({ is_open: !survey.is_open }),
                  survey.is_open ? "Questionnaire closed" : "Questionnaire opened", true)}>
                {survey.is_open ? "Close the questionnaire" : "Open the questionnaire"}
              </Button>
              {!confirmNewLink ? (
                <Button small variant="ghost" onClick={() => setConfirmNewLink(true)}>Make a new link</Button>
              ) : (
                <span className="row">
                  <span className="t-small">Every printed QR code and every link already sent stops working.</span>
                  <Button small variant="danger" loading={busy === "link"}
                    onClick={() => void run("link", replaceFeedbackLink, "New link made. Print the new QR code.",
                      true).then(() => setConfirmNewLink(false))}>
                    Yes, make a new link
                  </Button>
                  <Button small variant="ghost" onClick={() => setConfirmNewLink(false)}>Keep this link</Button>
                </span>
              )}
            </div>
          )}
        </div>
        {qrImage && (
          <figure className="feedback-qr">
            <img src={qrImage} alt={`QR code that opens ${link}`} width={180} height={180} />
            <figcaption className="t-micro">Scan to test it</figcaption>
          </figure>
        )}
      </div>

      <div className="stack-8">
        <h3 className="t-label">WhatsApp message to send with the link</h3>
        <div className="form-grid">
          <Field label="Family member's name" value={familyName} onChange={setFamilyName}
            placeholder="e.g. Mrs Dlamini" hint="Only for the message; it is not saved." />
          <div className="field">
            <label htmlFor="message-language">Language</label>
            <select id="message-language" value={messageLanguage}
              onChange={(e) => setMessageLanguage(e.target.value as "en" | "zu")}>
              <option value="en">English</option>
              <option value="zu">isiZulu</option>
            </select>
            <span className="field-hint" />
          </div>
        </div>
        <p className="feedback-message">{message}</p>
        <div className="row">
          <Button small onClick={() => void copy(message, "message")}>
            {copied === "message" ? "Copied" : "Copy message"}
          </Button>
          <a className="btn btn-small btn-ghost" target="_blank" rel="noopener noreferrer"
            href={`https://wa.me/?text=${encodeURIComponent(message)}`}>
            Open in WhatsApp
          </a>
        </div>
      </div>

      <hr className="divider" />

      {/* Wording and questions */}
      <div className="stack">
        <div className="stack-8">
          <h3 className="t-label">What families see</h3>
          <p className="t-small muted">
            The title and introduction open the page; then the questions, one at a time; then an
            optional name and cellphone number; then the thanks with the 24-hour line. Answering is
            voluntary. Changing a question never changes what earlier families were asked.
            {survey.updated_by && ` Last changed ${formatDate(survey.updated_at)} by ${survey.updated_by}.`}
          </p>
        </div>
        <fieldset className="stack-8" disabled={!canEdit} style={{ border: 0, padding: 0, margin: 0 }}>
          <div className="form-grid">
            <Field label="Title (English)" value={wording.title_en}
              onChange={(v) => { setWording({ ...wording, title_en: v }); setDirty(true); }} />
            <Field label="Title (isiZulu)" value={wording.title_zu}
              onChange={(v) => { setWording({ ...wording, title_zu: v }); setDirty(true); }} />
          </div>
          <div className="form-grid">
            <TextArea label="Introduction (English)" value={wording.intro_en}
              onChange={(v) => { setWording({ ...wording, intro_en: v }); setDirty(true); }} />
            <TextArea label="Introduction (isiZulu)" value={wording.intro_zu}
              onChange={(v) => { setWording({ ...wording, intro_zu: v }); setDirty(true); }} />
          </div>
        </fieldset>

        <FeedbackQuestionEditor key={editorKey} questions={questions} canEdit={canEdit}
          onChange={(next) => { setQuestions(next); setDirty(true); setSaved(null); }} />

        {canEdit && (
          <div className="row row-between">
            <Button small disabled={questions.length >= MAX_QUESTIONS}
              onClick={() => {
                setQuestions([...questions, newQuestion([...questions, ...survey.questions], data.answered_ids)]);
                setDirty(true);
              }}>
              Add a question
            </Button>
            <div className="row">
              {dirty && (
                <Button variant="ghost" onClick={() => reset(data)}>Undo changes</Button>
              )}
              <Button variant="primary" disabled={!dirty} loading={busy === "save"} loadingLabel="Saving…"
                onClick={() => void save()}>
                Save the questionnaire
              </Button>
            </div>
          </div>
        )}
      </div>

      <hr className="divider" />

      {/* What families said */}
      <div className="stack">
        <h3 className="t-label">Results</h3>
        <div className="metrics">
          <div className="fact">
            <span className="t-micro">Responses</span>
            <span className="metric-value">{summary.responses}</span>
          </div>
          <div className="fact">
            <span className="t-micro">Left a name or number</span>
            <span className="metric-value">{summary.named}</span>
          </div>
          <div className="fact">
            <span className="t-micro">Answered the short version</span>
            <span className="metric-value">{summary.short_version}</span>
          </div>
        </div>

        {summary.responses === 0 ? (
          <Empty title="No responses yet">
            Send the link with the WhatsApp message, or put the QR code where families will see it.
            Results appear here as answers arrive.
          </Empty>
        ) : (
          <div className="stack">
            {summary.questions.map((result, i) => {
              const question = survey.questions.find((q) => q.id === result.id);
              return question ? (
                <QuestionResults key={result.id} number={i + 1} question={question} result={result} />
              ) : null;
            })}
          </div>
        )}
      </div>

      {responses.length > 0 && (
        <div className="stack">
          <h3 className="t-label">Responses</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Family</th>
                  <th>Cellphone</th>
                  <th>Version</th>
                  <th>Came by</th>
                  <th><span className="sr-only">Answers</span></th>
                </tr>
              </thead>
              <tbody>
                {responses.map((r) => (
                  <Fragment key={r.id}>
                    <tr>
                      <td>{formatDate(r.created_at)}</td>
                      <td className="cell-name">{r.name ?? <span className="muted">Anonymous</span>}</td>
                      <td>{r.mobile ? <a href={`tel:${r.mobile}`}>{r.mobile}</a> : <span className="muted">—</span>}</td>
                      <td>{r.version === "short" ? "Short" : "Full"}</td>
                      <td>{r.source === "qr" ? "QR code" : "Link"}{r.language === "zu" ? " · isiZulu" : ""}</td>
                      <td>
                        <Button small variant="ghost" aria-expanded={openRow === r.id}
                          onClick={() => setOpenRow(openRow === r.id ? null : r.id)}>
                          {openRow === r.id ? "Hide answers" : "Answers"}
                        </Button>
                      </td>
                    </tr>
                    {openRow === r.id && (
                      <tr>
                        <td colSpan={6}>
                          <dl className="answers">
                            {r.answers.map((a) => (
                              <div key={a.id}>
                                <dt className="t-small muted">{a.question_en ?? a.question}</dt>
                                <dd>{a.label}</dd>
                              </div>
                            ))}
                          </dl>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
          {responses.length >= 200 && <p className="t-small muted">Showing the 200 most recent responses.</p>}
        </div>
      )}
    </section>
  );
}

/** One question's answers, counted: bars for choices and scales, a table for a grid. */
function QuestionResults({ number, question: q, result }: {
  number: number;
  question: FeedbackQuestion;
  result: FeedbackQuestionResult;
}) {
  const optionLabel = (value: string) => q.options?.find((o) => o.value === value)?.en ?? value;
  const rowLabel = (value: string) => q.rows?.find((r) => r.value === value)?.en ?? value;
  const counts = result.counts ?? {};
  const top = Math.max(1, ...Object.values(counts));

  return (
    <article className="question-result stack-8">
      <div className="row row-between">
        <strong>{number}. {q.text_en}</strong>
        <span className="t-small muted">{result.answered} answered</span>
      </div>
      {q.kind === "scale" && result.average !== null && (
        <p className="t-small">
          Average <strong>{result.average.toFixed(1)}</strong> out of {q.max}
          {result.nps !== null && <> · Recommend score (NPS) <strong>{result.nps > 0 ? "+" : ""}{result.nps}</strong></>}
        </p>
      )}
      {(q.kind === "choice" || q.kind === "scale") && result.answered > 0 && (
        <div className="stack-8">
          {Object.entries(counts).map(([value, n]) => (
            <div className="bar-row" key={value}>
              <span className="t-small">{q.kind === "scale" ? value : optionLabel(value)}</span>
              <div className="bar"><i style={{ width: `${(n / top) * 100}%` }} /></div>
              <span className="bar-count">{n}</span>
            </div>
          ))}
        </div>
      )}
      {q.kind === "grid" && result.grid && result.answered > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th><span className="sr-only">Item</span></th>
                {(q.options ?? []).map((o) => <th key={o.value}>{o.en}</th>)}
              </tr>
            </thead>
            <tbody>
              {Object.entries(result.grid).map(([row, cells]) => (
                <tr key={row}>
                  <td>{rowLabel(row)}</td>
                  {(q.options ?? []).map((o) => <td key={o.value}>{cells[o.value] ?? 0}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {q.kind === "text" && result.answered > 0 && (
        <p className="t-small muted">Open each response below to read what families wrote.</p>
      )}
    </article>
  );
}

function TextArea({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const id = `ta-${label.replace(/\W+/g, "-").toLowerCase()}`;
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <textarea id={id} rows={5} value={value} onChange={(e) => onChange(e.target.value)} />
      <span className="field-hint" />
    </div>
  );
}
