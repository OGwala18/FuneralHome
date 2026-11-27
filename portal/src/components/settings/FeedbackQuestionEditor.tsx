import { useId, useState } from "react";
import type { FeedbackChoice, FeedbackQuestion } from "@/lib/api";
import { Button, Field } from "@/components/ui";

/**
 * Editing the questionnaire's questions, in English and isiZulu.
 *
 * Lists (the options to pick from, the things to rate) are typed one per line,
 * English on the left and isiZulu on the right, line for line. Each option
 * keeps a stable code behind the scenes, worked out from its English wording,
 * so the results keep counting the same answer when a question is reordered
 * or a different option is reworded.
 *
 * What is typed in a list box is kept as typed (blank lines included) while
 * editing; the parent remounts this editor (a new `key`) to start again from
 * the saved questions.
 */

export const MAX_QUESTIONS = 15;

type KindChoice = "choice" | "scale5" | "scale10" | "grid" | "text";


const KINDS: { value: KindChoice; label: string }[] = [
  { value: "choice", label: "Pick one answer" },
  { value: "scale5", label: "Scale, 1 to 5" },
  { value: "scale10", label: "Scale, 0 to 10" },
  { value: "grid", label: "Rate several things" },
  { value: "text", label: "Written answer" },
];

const kindOf = (q: FeedbackQuestion): KindChoice =>
  q.kind === "scale" ? (q.max === 10 ? "scale10" : "scale5") : q.kind;

const slug = (text: string) =>
  text.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40);

/** Lines of English and isiZulu back into options.
 *
 * `known` is every option this list has had: as saved first, then as currently
 * edited. A line whose English matches one keeps its code, wherever the line
 * moved to, so the results keep counting it. A new or reworded line gets a new
 * code that no known option has ever used, so it never inherits another
 * option's results. */
export const toChoices = (en: string, zu: string, known: FeedbackChoice[] = []): FeedbackChoice[] => {
  const enLines = en.split("\n").map((l) => l.trim());
  const zuLines = zu.split("\n").map((l) => l.trim());
  const reserved = new Set(known.map((k) => k.value));
  const used = new Set<string>();
  const out: FeedbackChoice[] = [];
  enLines.forEach((line, i) => {
    if (!line) return;
    const kept = known.find((k) => k.en === line && !used.has(k.value));
    let value = kept?.value ?? "";
    if (!value) {
      const base = (slug(line) || `option_${i + 1}`).slice(0, 36);
      value = base;
      let n = 2;
      while (used.has(value) || reserved.has(value)) value = `${base}_${n++}`;
    }
    used.add(value);
    out.push({ value, en: line, zu: zuLines[i] || null });
  });
  return out;
};

/** Several lists of options as one, the first seen of each code winning. */
const merged = (...lists: (FeedbackChoice[] | null | undefined)[]): FeedbackChoice[] => {
  const byValue = new Map<string, FeedbackChoice>();
  for (const choice of lists.flatMap((l) => l ?? [])) {
    if (!byValue.has(choice.value)) byValue.set(choice.value, choice);
  }
  return [...byValue.values()];
};

const lines = (items: FeedbackChoice[] | null | undefined, lang: "en" | "zu") =>
  (items ?? []).map((c) => (lang === "en" ? c.en : c.zu ?? "")).join("\n");

const DEFAULT_GRID_OPTIONS: FeedbackChoice[] = [
  { value: "excellent", en: "Excellent", zu: "Kuhle kakhulu" },
  { value: "good", en: "Good", zu: "Kuhle" },
  { value: "fair", en: "Fair", zu: "Kuphakathi" },
  { value: "poor", en: "Poor", zu: "Kubi" },
];

/** A question changed to another kind gets sensible starting values for it. */
const changeKind = (q: FeedbackQuestion, kind: KindChoice): FeedbackQuestion => {
  const base: FeedbackQuestion = { id: q.id, text_en: q.text_en, text_zu: q.text_zu,
    short: q.short, required: q.required, kind: "text" };
  switch (kind) {
    case "choice":
      return { ...base, kind: "choice", options: q.options?.length ? q.options
        : [{ value: "yes", en: "Yes", zu: "Yebo" }, { value: "no", en: "No", zu: "Cha" }] };
    case "grid":
      return { ...base, kind: "grid", rows: q.rows?.length ? q.rows : [{ value: "item", en: "Item", zu: null }],
        options: q.options?.length ? q.options : DEFAULT_GRID_OPTIONS };
    case "scale5":
      return { ...base, kind: "scale", min: 1, max: 5,
        low_en: q.low_en ?? "Very unhappy", high_en: q.high_en ?? "Very satisfied",
        low_zu: q.low_zu ?? null, high_zu: q.high_zu ?? null };
    case "scale10":
      return { ...base, kind: "scale", min: 0, max: 10,
        low_en: q.low_en ?? "Not at all likely", high_en: q.high_en ?? "Extremely likely",
        low_zu: q.low_zu ?? null, high_zu: q.high_zu ?? null };
    default:
      return base;
  }
};

/** A new question's id: one past the highest ever used, counting questions
 *  removed since but still answered (`taken`), so it never inherits their
 *  results. */
export const newQuestion = (existing: FeedbackQuestion[], taken: string[] = []): FeedbackQuestion => {
  const numbers = [...existing.map((q) => q.id), ...taken]
    .map((id) => /^q(\d+)$/.exec(id)?.[1])
    .filter((n): n is string => Boolean(n))
    .map(Number);
  const next = Math.max(0, ...numbers) + 1;
  return { id: `q${next}`, kind: "text", text_en: "", text_zu: null, short: false, required: false };
};

/** What the API will refuse, said per question before sending. */
export const problemsIn = (questions: FeedbackQuestion[]): string[] => {
  const out: string[] = [];
  questions.forEach((q, i) => {
    const n = `Question ${i + 1}`;
    if (q.text_en.trim().length < 3) out.push(`${n}: write the question in English (at least 3 letters).`);
    if (q.kind === "choice" || q.kind === "grid") {
      const count = q.options?.length ?? 0;
      if (count < 2) out.push(`${n}: give at least two ${q.kind === "grid" ? "ratings" : "answers"} to pick from.`);
      if (count > 12) out.push(`${n}: at most 12 ${q.kind === "grid" ? "ratings" : "answers"}.`);
    }
    if (q.kind === "grid") {
      const rows = q.rows?.length ?? 0;
      if (rows < 1) out.push(`${n}: give at least one thing to rate.`);
      if (rows > 12) out.push(`${n}: at most 12 things to rate.`);
    }
  });
  if (questions.length < 1) out.push("Keep at least one question.");
  if (questions.length > MAX_QUESTIONS) out.push(`At most ${MAX_QUESTIONS} questions.`);
  return out;
};

type ListName = "options_en" | "options_zu" | "rows_en" | "rows_zu";
type Drafts = Record<string, Partial<Record<ListName, string>>>;

export default function FeedbackQuestionEditor({ questions, onChange, canEdit }: {
  questions: FeedbackQuestion[];
  onChange: (next: FeedbackQuestion[]) => void;
  canEdit: boolean;
}) {
  // The list boxes' text as typed, per question.
  const [drafts, setDrafts] = useState<Drafts>({});
  // The questions as saved, when this editor opened (it is remounted after a
  // save or Undo), so option codes survive any amount of editing in between.
  const [saved] = useState(() => new Map(questions.map((q) => [q.id, q])));
  const update = (index: number, next: FeedbackQuestion) =>
    onChange(questions.map((q, i) => (i === index ? next : q)));

  const listText = (q: FeedbackQuestion, name: ListName) => {
    const typed = drafts[q.id]?.[name];
    if (typed !== undefined) return typed;
    const [list, lang] = name.split("_") as ["options" | "rows", "en" | "zu"];
    return lines(q[list], lang);
  };

  const editList = (index: number, name: ListName, text: string) => {
    const q = questions[index];
    const list = name.startsWith("rows") ? "rows" : "options";
    const enName = `${list}_en` as ListName;
    const zuName = `${list}_zu` as ListName;
    // Both boxes of the list are kept exactly as they stand, so editing the
    // English never shifts the isiZulu lines (or the other way round).
    const en = name === enName ? text : listText(q, enName);
    const zu = name === zuName ? text : listText(q, zuName);
    setDrafts({ ...drafts, [q.id]: { ...drafts[q.id], [enName]: en, [zuName]: zu } });
    update(index, { ...q, [list]: toChoices(en, zu, merged(saved.get(q.id)?.[list], q[list])) });
  };

  const setKind = (index: number, kind: KindChoice) => {
    const q = questions[index];
    setDrafts({ ...drafts, [q.id]: {} });
    update(index, changeKind(q, kind));
  };
  const move = (index: number, by: -1 | 1) => {
    const next = [...questions];
    const [item] = next.splice(index, 1);
    next.splice(index + by, 0, item);
    onChange(next);
  };

  return (
    <div className="stack">
      {questions.map((q, index) => (
        <fieldset key={q.id} className="question-edit stack-8" disabled={!canEdit}>
          <legend className="t-small">
            Question {index + 1}
            {q.short && <span className="muted"> · in the short version</span>}
          </legend>

          <div className="form-grid">
            <Field label="Question (English)" value={q.text_en}
              onChange={(v) => update(index, { ...q, text_en: v })} />
            <Field label="Question (isiZulu)" value={q.text_zu ?? ""}
              onChange={(v) => update(index, { ...q, text_zu: v || null })}
              hint="Optional. Blank shows the English." />
            <div className="field">
              <label htmlFor={`kind-${q.id}`}>Kind of answer</label>
              <select id={`kind-${q.id}`} value={kindOf(q)}
                onChange={(e) => setKind(index, e.target.value as KindChoice)}>
                {KINDS.map((k) => <option key={k.value} value={k.value}>{k.label}</option>)}
              </select>
              <span className="field-hint" />
            </div>
          </div>

          {(q.kind === "choice" || q.kind === "grid") && (
            <div className="form-grid">
              {q.kind === "grid" && (
                <>
                  <ListField label="Things to rate (English), one per line"
                    value={listText(q, "rows_en")} onChange={(v) => editList(index, "rows_en", v)} />
                  <ListField label="Things to rate (isiZulu), line for line"
                    value={listText(q, "rows_zu")} onChange={(v) => editList(index, "rows_zu", v)} />
                </>
              )}
              <ListField label={`${q.kind === "grid" ? "Ratings" : "Answers to pick from"} (English), one per line`}
                value={listText(q, "options_en")} onChange={(v) => editList(index, "options_en", v)} />
              <ListField label={`${q.kind === "grid" ? "Ratings" : "Answers"} (isiZulu), line for line`}
                value={listText(q, "options_zu")} onChange={(v) => editList(index, "options_zu", v)} />
            </div>
          )}

          {q.kind === "scale" && (
            <div className="form-grid">
              <Field label={`What ${q.min} means (English)`} value={q.low_en ?? ""}
                onChange={(v) => update(index, { ...q, low_en: v || null })} />
              <Field label={`What ${q.min} means (isiZulu)`} value={q.low_zu ?? ""}
                onChange={(v) => update(index, { ...q, low_zu: v || null })} />
              <Field label={`What ${q.max} means (English)`} value={q.high_en ?? ""}
                onChange={(v) => update(index, { ...q, high_en: v || null })} />
              <Field label={`What ${q.max} means (isiZulu)`} value={q.high_zu ?? ""}
                onChange={(v) => update(index, { ...q, high_zu: v || null })} />
            </div>
          )}

          <div className="row row-between">
            <div className="row">
              <label className="choice">
                <input type="checkbox" checked={Boolean(q.short)}
                  onChange={(e) => update(index, { ...q, short: e.target.checked })} />
                <span className="t-small">In the short version</span>
              </label>
              <label className="choice">
                <input type="checkbox" checked={Boolean(q.required)}
                  onChange={(e) => update(index, { ...q, required: e.target.checked })} />
                <span className="t-small">Must be answered</span>
              </label>
            </div>
            {canEdit && (
              <div className="row">
                <Button small variant="ghost" disabled={index === 0} onClick={() => move(index, -1)}
                  aria-label={`Move question ${index + 1} up`}>↑ Up</Button>
                <Button small variant="ghost" disabled={index === questions.length - 1}
                  onClick={() => move(index, 1)} aria-label={`Move question ${index + 1} down`}>↓ Down</Button>
                {questions.length > 1 && (
                  <Button small variant="ghost" onClick={() => onChange(questions.filter((_, i) => i !== index))}>
                    Remove
                  </Button>
                )}
              </div>
            )}
          </div>
        </fieldset>
      ))}
    </div>
  );
}

function ListField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  const id = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <textarea id={id} rows={Math.max(3, value.split("\n").length + 1)} value={value}
        onChange={(e) => onChange(e.target.value)} />
      <span className="field-hint" />
    </div>
  );
}
