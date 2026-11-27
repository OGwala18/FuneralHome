import { useRef, useState, type ChangeEvent } from "react";
import {
  checkMemberUpload,
  importMemberUpload,
  type UploadCheck,
  type UploadImport,
  type UploadPolicy,
} from "@/lib/api";
import { formatDate, formatMoney } from "@/lib/derive";
import { Badge, Button, Empty, Notice } from "@/components/ui";

/**
 * Settings > User upload: policies into the member book from a spreadsheet.
 *
 *   1 Download the template   2 Fill it in   3 Upload: every row is checked
 *   4 Verify, then add the policies that passed
 *
 * The owner's rules (26 Nov 2026): a policy is added only when all its rows
 * pass; the rest are listed by row and reason to fix and upload again. A blank
 * policy number belongs to the policy above. Premium and cover come from the
 * sheet. Uploading the same sheet again skips what is already in the book.
 *
 * The file never leaves this page except to the API, which checks it again
 * from scratch before adding anything.
 */

const TEMPLATE = "/templates/induduzo-member-upload-template.xlsx";

const TYPE_LABEL: Record<string, string> = {
  main_member: "Main member", spouse: "Spouse", child: "Child",
  extended: "Extended", beneficiary: "Beneficiary",
};

type View = "fix" | "ready" | "exists";

export default function UserUpload({ canEdit }: { canEdit: boolean }) {
  const [file, setFile] = useState<File | null>(null);
  const [check, setCheck] = useState<UploadCheck | null>(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [verified, setVerified] = useState(false);
  const [adding, setAdding] = useState(false);
  const [result, setResult] = useState<UploadImport | null>(null);
  const [view, setView] = useState<View>("fix");
  const input = useRef<HTMLInputElement>(null);

  const runCheck = async (chosen: File) => {
    setChecking(true);
    setError(null);
    setResult(null);
    setVerified(false);
    try {
      const next = await checkMemberUpload(chosen);
      setCheck(next);
      setView(next.to_fix > 0 ? "fix" : next.ready > 0 ? "ready" : "exists");
    } catch (e) {
      setCheck(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setChecking(false);
    }
  };

  const choose = (event: ChangeEvent<HTMLInputElement>) => {
    const chosen = event.target.files?.[0];
    event.target.value = "";
    if (!chosen) return;
    setFile(chosen);
    void runCheck(chosen);
  };

  const add = async () => {
    if (!file || !check) return;
    setAdding(true);
    setError(null);
    try {
      const done = await importMemberUpload(file, check.checksum);
      setResult(done);
      setCheck(done.check);
      setVerified(false);
      setView(done.check.to_fix > 0 ? "fix" : "exists");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setAdding(false);
    }
  };

  if (!canEdit) {
    return (
      <Notice title="Only admins and owners add members"
        detail="Ask an admin or owner to upload the spreadsheet." />
    );
  }

  const shown = check?.policies.filter((p) => p.state === view) ?? [];

  return (
    <div className="stack" style={{ gap: "var(--s24)" }}>
      <section className="card stack" aria-labelledby="upload-steps">
        <h2 className="t-title" id="upload-steps">Add members from a spreadsheet</h2>
        <ol className="upload-steps">
          <li>
            <strong>Download the template</strong> and fill in one row per person: the main member
            first, then everyone else on that policy. Put the policy number, entry date, product,
            premium and cover on the main member's row; leave the policy number blank on the rows
            under it.
            <div className="row" style={{ marginTop: "var(--s8)" }}>
              <a className="btn btn-small" href={TEMPLATE} download>Download the template</a>
            </div>
          </li>
          <li>
            <strong>Upload it.</strong> Every row is checked: ID numbers (13 digits, a real date,
            the right check digit), dates of birth against the ID, ages, types, plans, amounts and
            cell numbers. Bank details are refused: the system never stores them.
            <div className="row" style={{ marginTop: "var(--s8)" }}>
              <input ref={input} type="file" className="sr-only"
                accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                onChange={choose} />
              <Button variant="primary" small loading={checking} loadingLabel="Checking…"
                onClick={() => input.current?.click()}>
                {file ? "Upload a different sheet" : "Upload the filled-in sheet"}
              </Button>
              {file && check && (
                <Button small variant="ghost" disabled={checking} onClick={() => void runCheck(file)}>
                  Check {file.name} again
                </Button>
              )}
            </div>
          </li>
          <li>
            <strong>Fix and verify.</strong> Policies with a problem are listed by row and reason.
            Fix them in the sheet and upload it again, or add the ready ones now and the rest later.
            A policy already in the member book is never added twice.
          </li>
        </ol>
      </section>

      {error && <Notice tone="error" title="Not done" detail={error} />}

      {result && (
        <Notice
          tone={Object.keys(result.failed).length ? "warn" : "success"}
          title={`${result.added.length} ${result.added.length === 1 ? "policy" : "policies"} added to the member book`}
          detail={
            <>
              {result.added.length > 0 && <>Added: {result.added.join(", ")}. Find them in Members.</>}
              {Object.entries(result.failed).map(([number, why]) => (
                <span key={number} style={{ display: "block" }}>{number}: {why}</span>
              ))}
              {result.check.to_fix > 0 && ` ${result.check.to_fix} still need fixing in the sheet.`}
            </>
          }
        />
      )}

      {check && (
        <section className="card stack" aria-labelledby="upload-results">
          <div className="card-head">
            <div className="stack-8">
              <h2 className="t-title" id="upload-results">Check of {file?.name ?? "the sheet"}</h2>
              <p className="t-small muted">
                {check.rows} {check.rows === 1 ? "row" : "rows"}, {check.policies.length}{" "}
                {check.policies.length === 1 ? "policy" : "policies"}.
                {check.ignored_columns.length > 0 &&
                  ` Not used: ${check.ignored_columns.join(", ")}.`}
              </p>
            </div>
          </div>

          {check.file_problems.map((p) => (
            <Notice key={`${p.row}-${p.column}`} tone="error" title="The sheet cannot be read as it is"
              detail={`Row ${p.row}${p.column ? ` · ${p.column}` : ""}: ${p.message}`} />
          ))}

          <div className="settings-sections" role="tablist" aria-label="Policies">
            {([
              ["fix", `Need fixing (${check.to_fix})`],
              ["ready", `Ready to add (${check.ready})`],
              ["exists", `Already in the book (${check.already_in_book})`],
            ] as [View, string][]).map(([id, label]) => (
              <button key={id} type="button" role="tab" aria-selected={view === id}
                className={`btn btn-small${view === id ? " btn-selected" : ""}`}
                onClick={() => setView(id)}>
                {label}
              </button>
            ))}
          </div>

          {shown.length === 0 ? (
            <Empty title={view === "fix" ? "Nothing to fix" : view === "ready" ? "Nothing ready to add"
              : "None of these are in the book yet"} />
          ) : (
            <div className="stack">
              {shown.map((p) => <PolicyResult key={p.policy_number} policy={p} />)}
            </div>
          )}

          {check.ready > 0 && (
            <div className="verify-box stack">
              <label className="choice">
                <input type="checkbox" checked={verified} onChange={(e) => setVerified(e.target.checked)} />
                <span>
                  I have checked the {check.ready} ready {check.ready === 1 ? "policy" : "policies"} against
                  the paper application forms.
                </span>
              </label>
              <div className="row">
                <Button variant="primary" disabled={!verified} loading={adding} loadingLabel="Adding…"
                  onClick={() => void add()}>
                  Add {check.ready} {check.ready === 1 ? "policy" : "policies"} to the member book
                </Button>
                {check.to_fix > 0 && (
                  <span className="t-small muted">
                    The {check.to_fix} that need fixing are not added.
                  </span>
                )}
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function PolicyResult({ policy: p }: { policy: UploadPolicy }) {
  const tone = p.state === "ready" ? "success" : p.state === "fix" ? "overdue" : "neutral";
  const label = p.state === "ready" ? "Ready" : p.state === "fix" ? "Needs fixing" : "Already in the book";
  return (
    <article className="upload-policy">
      <div className="row row-between">
        <div className="row">
          <strong className="ref">{p.policy_number}</strong>
          <Badge tone={tone}>{label}</Badge>
          <span className="t-small muted">
            Rows {p.first_row}{p.last_row !== p.first_row ? `–${p.last_row}` : ""}
          </span>
        </div>
        <span className="t-small muted">
          {[p.product, p.premium_cents !== null ? `${formatMoney(p.premium_cents)} a month` : null,
            p.cover_cents !== null ? `cover ${formatMoney(p.cover_cents)}` : null,
            p.entry_date ? `from ${formatDate(p.entry_date)}` : null].filter(Boolean).join(" · ")}
        </span>
      </div>
      <p className="t-small">
        {p.lives.map((life) => `${life.name || "(no name)"}${life.member_type ? ` (${TYPE_LABEL[life.member_type]})` : ""}`).join(", ")}
      </p>
      {p.problems.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Row</th><th>Column</th><th>What is wrong</th></tr>
            </thead>
            <tbody>
              {p.problems.map((x, i) => (
                <tr key={i}>
                  <td>{x.row}</td>
                  <td>{x.column}</td>
                  <td>{x.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </article>
  );
}
