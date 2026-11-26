import { Fragment, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  fetchFeedback,
  replaceFeedbackLink,
  updateFeedbackSurvey,
  type FeedbackOverview,
  type FeedbackQuestion,
  type FeedbackQuestionKind,
} from "@/lib/api";
import { formatDate } from "@/lib/derive";
import { qrCanvas } from "@/lib/qr";
import { Badge, Button, Empty, Field, Notice, Select, Skeleton } from "@/components/ui";

/**
 * The private feedback questionnaire.
 *
 * It is not on the website: it opens only from its own link, so the office
 * hands it out, as a QR code on a counter card or a link passed on WhatsApp.
 * The QR code adds ?via=qr, so the responses show which way people came.
 *
 * "Make a new link" retires the old one at once: every printed QR code stops
 * working. That is the point when a link has spread too far, and the reason
 * the button asks first.
 */

const KINDS: { value: FeedbackQuestionKind; label: string }[] = [
  { value: "text", label: "Written answer" },
  { value: "yes_no", label: "Yes or no" },
  { value: "scale", label: "1 to 5 scale" },
];

const MAX_QUESTIONS = 10;

const answerLabel = (kind: FeedbackQuestionKind, answer: string) => {
  if (kind === "yes_no") return answer === "yes" ? "Yes" : answer === "no" ? "No" : "—";
  if (kind === "scale") return answer ? `${answer} / 5` : "—";
  return answer || "—";
};

const stars = (n: number) => "★".repeat(n) + "☆".repeat(5 - n);

export default function FeedbackSettings() {
  const [data, setData] = useState<FeedbackOverview | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [questions, setQuestions] = useState<FeedbackQuestion[]>([]);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState<"" | "questions" | "open" | "link">("");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [confirmNewLink, setConfirmNewLink] = useState(false);
  const [openRow, setOpenRow] = useState<string | null>(null);

  const load = () => {
    setLoadError(null);
    fetchFeedback()
      .then((next) => {
        setData(next);
        setQuestions(next.survey.questions);
        setDirty(false);
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : String(e)));
  };
  useEffect(load, []);

  const qrLink = data ? `${data.survey.link}?via=qr` : "";
  const qrImage = useMemo(() => (qrLink ? qrCanvas(qrLink, 600).toDataURL("image/png") : ""), [qrLink]);

  if (loadError) {
    return (
      <Notice tone="error" title="Could not load the questionnaire." detail={loadError}
        action={<Button small onClick={load}>Try again</Button>} />
    );
  }
  if (!data) return <section className="card"><Skeleton rows={6} /></section>;

  const { survey, summary, responses, can_edit: canEdit } = data;

  const run = async (what: typeof busy, action: () => Promise<unknown>, done: string) => {
    setBusy(what);
    setError(null);
    setFieldErrors({});
    setSaved(null);
    try {
      await action();
      setSaved(done);
      load();
    } catch (e) {
      if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("");
    }
  };

  const change = (index: number, patch: Partial<FeedbackQuestion>) => {
    setQuestions((qs) => qs.map((q, i) => (i === index ? { ...q, ...patch } : q)));
    setDirty(true);
    setSaved(null);
  };

  const addQuestion = () => {
    const used = new Set(questions.map((q) => q.id));
    let n = 1;
    while (used.has(`q${n}`)) n += 1;
    setQuestions((qs) => [...qs, { id: `q${n}`, kind: "text", text_en: "", text_zu: null }]);
    setDirty(true);
  };

  const removeQuestion = (index: number) => {
    setQuestions((qs) => qs.filter((_, i) => i !== index));
    setDirty(true);
  };

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(survey.link);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2500);
    } catch {
      setError("Could not copy. Select the link and copy it by hand.");
    }
  };

  const downloadQr = () => {
    const link = document.createElement("a");
    link.href = qrCanvas(qrLink, 1200).toDataURL("image/png");
    link.download = "induduzo-feedback-qr.png";
    link.click();
  };

  const maxRating = Math.max(1, ...Object.values(summary.by_rating));

  return (
    <section className="card stack" aria-labelledby="feedback-title">
      <div className="stack-8">
        <h2 className="t-title" id="feedback-title">Feedback questionnaire</h2>
        <p className="t-small muted">
          A private page on the website. It is not in the menu and search engines are told to skip
          it: people reach it only through this link or its QR code.
        </p>
      </div>

      {saved && <Notice tone="success" title={saved} />}
      {error && <Notice tone="error" title="Not saved" detail={error} />}

      {/* The link and its QR code */}
      <div className="feedback-link">
        <div className="stack grow">
          <div className="row">
            <Badge tone={survey.is_open ? "success" : "neutral"}>{survey.is_open ? "Open" : "Closed"}</Badge>
            <span className="t-small muted">
              {survey.is_open ? "Anyone with the link can answer." : "The link shows “page not found” until it is opened again."}
            </span>
          </div>
          <code className="feedback-url">{survey.link}</code>
          <div className="row">
            <Button small onClick={() => void copyLink()}>{copied ? "Copied" : "Copy link"}</Button>
            <Button small onClick={downloadQr}>Download QR code</Button>
            <a className="btn btn-small btn-ghost" href={survey.link} target="_blank" rel="noopener noreferrer">
              Open the page
            </a>
          </div>
          {canEdit && (
            <div className="row">
              <Button small variant={survey.is_open ? "secondary" : "primary"} loading={busy === "open"}
                onClick={() => void run("open", () => updateFeedbackSurvey({ is_open: !survey.is_open }),
                  survey.is_open ? "Questionnaire closed" : "Questionnaire opened")}>
                {survey.is_open ? "Close the questionnaire" : "Open the questionnaire"}
              </Button>
              {!confirmNewLink ? (
                <Button small variant="ghost" onClick={() => setConfirmNewLink(true)}>Make a new link</Button>
              ) : (
                <span className="row">
                  <span className="t-small">Every printed QR code and shared link stops working.</span>
                  <Button small variant="danger" loading={busy === "link"}
                    onClick={() => void run("link", replaceFeedbackLink, "New link made. Print the new QR code.")
                      .then(() => setConfirmNewLink(false))}>
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
            <img src={qrImage} alt={`QR code that opens ${survey.link}`} width={180} height={180} />
            <figcaption className="t-micro">Scan to test it</figcaption>
          </figure>
        )}
      </div>

      <hr className="divider" />

      {/* The questions */}
      <div className="stack">
        <div className="stack-8">
          <h3 className="t-label">Questions</h3>
          <p className="t-small muted">
            People answer these after giving their name, surname and mobile number, then rate the
            service from 1 to 5. Changing a question never changes what earlier people were asked.
            {survey.updated_by && ` Last changed ${formatDate(survey.updated_at)} by ${survey.updated_by}.`}
          </p>
        </div>

        {questions.map((q, index) => (
          <fieldset key={q.id} className="question-edit">
            <legend className="t-small">Question {index + 1}</legend>
            <div className="form-grid">
              <Field label="Question (English)" value={q.text_en} disabled={!canEdit}
                onChange={(v) => change(index, { text_en: v })}
                error={fieldErrors[`questions.${index}.text_en`]} />
              <Field label="Question (isiZulu)" value={q.text_zu ?? ""} disabled={!canEdit}
                onChange={(v) => change(index, { text_zu: v || null })}
                hint="Optional. Blank shows the English." />
              <Select label="Kind of answer" value={q.kind} disabled={!canEdit} options={KINDS}
                onChange={(v) => change(index, { kind: v as FeedbackQuestionKind })} />
            </div>
            {canEdit && questions.length > 1 && (
              <Button small variant="ghost" onClick={() => removeQuestion(index)}>Remove question {index + 1}</Button>
            )}
          </fieldset>
        ))}

        {canEdit && (
          <div className="row row-between">
            <Button small disabled={questions.length >= MAX_QUESTIONS} onClick={addQuestion}>
              Add a question
            </Button>
            <div className="row">
              {dirty && (
                <Button variant="ghost" onClick={() => { setQuestions(survey.questions); setDirty(false); }}>
                  Undo changes
                </Button>
              )}
              <Button variant="primary" disabled={!dirty} loading={busy === "questions"} loadingLabel="Saving…"
                onClick={() => void run("questions",
                  () => updateFeedbackSurvey({
                    questions: questions.map((q) => ({ ...q, text_en: q.text_en.trim(), text_zu: q.text_zu?.trim() || null })),
                  }),
                  "Questions saved. The page asks them from now on.")}>
                Save questions
              </Button>
            </div>
          </div>
        )}
      </div>

      <hr className="divider" />

      {/* What people said */}
      <div className="stack">
        <h3 className="t-label">Responses</h3>
        <div className="metrics">
          <div className="fact">
            <span className="t-micro">Responses</span>
            <span className="metric-value">{summary.responses}</span>
          </div>
          <div className="fact">
            <span className="t-micro">Average rating</span>
            <span className="metric-value">
              {summary.average_rating !== null ? `${summary.average_rating.toFixed(1)} / 5` : "—"}
            </span>
            <span className="t-small muted">from {summary.rated} rating{summary.rated === 1 ? "" : "s"}</span>
          </div>
        </div>
        {summary.rated > 0 && (
          <div className="stack-8" aria-label="Ratings">
            {["5", "4", "3", "2", "1"].map((n) => (
              <div className="bar-row" key={n}>
                <span className="t-small">{stars(Number(n))}</span>
                <div className="bar"><i style={{ width: `${(summary.by_rating[n] / maxRating) * 100}%` }} /></div>
                <span className="bar-count">{summary.by_rating[n]}</span>
              </div>
            ))}
          </div>
        )}

        {responses.length === 0 ? (
          <Empty title="No responses yet">
            Share the link or put the QR code where families will see it. Answers appear here as they arrive.
          </Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Person</th>
                  <th>Mobile</th>
                  <th>Rating</th>
                  <th>Came by</th>
                  <th><span className="sr-only">Answers</span></th>
                </tr>
              </thead>
              <tbody>
                {responses.map((r) => (
                  <Fragment key={r.id}>
                    <tr>
                      <td>{formatDate(r.created_at)}</td>
                      <td className="cell-name">{r.first_name} {r.surname}</td>
                      <td><a href={`tel:${r.mobile}`}>{r.mobile}</a></td>
                      <td>{r.rating ? <span title={`${r.rating} out of 5`}>{stars(r.rating)}</span> : <span className="muted">Not rated</span>}</td>
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
                                <dt className="t-small muted">{a.question}</dt>
                                <dd>{answerLabel(a.kind, a.answer)}</dd>
                              </div>
                            ))}
                            {r.rating_comment && (
                              <div>
                                <dt className="t-small muted">Added with the rating</dt>
                                <dd>{r.rating_comment}</dd>
                              </div>
                            )}
                          </dl>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {responses.length >= 200 && (
          <p className="t-small muted">Showing the 200 most recent responses.</p>
        )}
      </div>
    </section>
  );
}
