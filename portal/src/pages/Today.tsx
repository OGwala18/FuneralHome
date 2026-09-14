import { useMemo, useState } from "react";
import type { EnquiryRow } from "@/lib/api";
import {
  area,
  label,
  buildQueue,
  fullName,
  planOf,
  queueProgress,
  toneForRow,
  waitingFor,
} from "@/lib/derive";
import { navigate } from "@/lib/router";
import { useEnquiries } from "@/lib/useEnquiries";
import { Badge, Button, Empty, Fact, Notice, Skeleton } from "@/components/ui";

/**
 * The call desk. One question answered above everything else: who do I phone
 * next, and what do I need to know before I do?
 *
 * Layout follows the eye. The queue is on the left because it is the thing
 * being worked through; the person is in the middle because that is the task;
 * context sits on the right, close enough to read mid-call without scrolling
 * (Proximity, and Minimize Target Distance for the Call button).
 */

const QUEUE_TONE = { overdue: "overdue", due: "due", neutral: "neutral" } as const;

export default function Today({ canEdit }: { canEdit: boolean }) {
  // A generous window: the queue is grouped and prioritised client-side, so it
  // needs the open enquiries rather than the newest 25.
  const { rows, loading, error, reload } = useEnquiries({
    sort: "created_at",
    descending: false,
    limit: 200,
  });

  const [selectedId, setSelectedId] = useState<string | null>(null);

  const groups = useMemo(() => buildQueue(rows), [rows]);
  const progress = useMemo(() => queueProgress(rows), [rows]);

  const queued = useMemo(() => groups.flatMap((g) => g.rows), [groups]);
  const selected: EnquiryRow | undefined =
    queued.find((r) => r.id === selectedId) ?? queued[0];

  const remaining = queued.length;

  if (loading && rows.length === 0) {
    return (
      <div className="page">
        <div className="page-head">
          <div className="page-head-text">
            <h1 className="t-heading">Today</h1>
            <p className="muted">Getting your call list.</p>
          </div>
        </div>
        <div className="card">
          <Skeleton rows={8} />
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-text">
          <h1 className="t-heading">Good day</h1>
          <p className="muted">
            {remaining === 0
              ? "Nothing is waiting for a call."
              : `${remaining} ${remaining === 1 ? "person is" : "people are"} waiting to hear from you. Start at the top.`}
          </p>
        </div>
        {selected && (
          <Button variant="primary" onClick={() => navigate({ name: "person", id: selected.id })}>
            Open record
          </Button>
        )}
      </div>

      {error && (
        <div style={{ marginBottom: "var(--s16)" }}>
          <Notice
            tone="error"
            title="Could not load the call list."
            detail={error}
            action={
              <Button small onClick={() => void reload()}>
                Try again
              </Button>
            }
          />
        </div>
      )}

      {/* Zeigarnik: the day's shape, visible. Progress is derived from status,
          which is the only completion signal the API exposes. */}
      <div className="card card-tight" style={{ marginBottom: "var(--s24)" }}>
        <div className="row row-between">
          <span className="t-label">
            {progress.handled} of {progress.total} enquiries moved past first contact
          </span>
          <div className="progress" role="img" aria-label={`${progress.percent} percent handled`}>
            <i style={{ width: `${progress.percent}%` }} />
          </div>
          <span className="t-small muted">{remaining} still open</span>
        </div>
      </div>

      {queued.length === 0 ? (
        <div className="card">
          <Empty title="The call list is clear">
            Every enquiry has been picked up. New ones arrive here as people register on the
            website.
          </Empty>
        </div>
      ) : (
        <div className="split">
          <div className="stack">
            {selected && <PersonPanel row={selected} canEdit={canEdit} />}
          </div>

          <div className="card">
            <div className="card-head">
              <h2 className="t-section">Up next</h2>
              <span className="t-small muted">{remaining} left</span>
            </div>

            {groups.map((group) => (
              <section className="queue-group" key={group.key} aria-label={group.title}>
                <div className="queue-group-head">
                  <span className="t-micro">{group.title}</span>
                  <Badge tone={QUEUE_TONE[group.tone]}>{group.rows.length}</Badge>
                </div>
                <p className="t-small muted" style={{ margin: "0 0 var(--s8)" }}>
                  {group.note}
                </p>

                {group.rows.map((row) => (
                  <button
                    type="button"
                    key={row.id}
                    className="queue-item"
                    aria-current={selected?.id === row.id}
                    onClick={() => setSelectedId(row.id)}
                  >
                    <span className="queue-name">{fullName(row)}</span>
                    <div className="row" style={{ gap: "var(--s8)", marginTop: 2 }}>
                      <span className="t-small muted">{planOf(row)}</span>
                      <span className="t-small muted">·</span>
                      <span className="t-small muted">{waitingFor(row.created_at)}</span>
                    </div>
                  </button>
                ))}
              </section>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* --------------------------------------------------------------- Person --- */

function PersonPanel({ row, canEdit }: { row: EnquiryRow; canEdit: boolean }) {
  const tone = toneForRow(row);

  return (
    <>
      <div className="card">
        <div className="card-head">
          <div className="stack-8">
            <h2 className="t-title">{fullName(row)}</h2>
            <span className="t-small muted">
              <span className="ref">{row.reference}</span> · {area(row)} · Enquiry received{" "}
              {waitingFor(row.created_at).toLowerCase()}
            </span>
          </div>
          <Badge tone={tone === "overdue" ? "overdue" : tone === "due" ? "due" : "neutral"}>
            {tone === "overdue" ? "Overdue" : tone === "due" ? "Waiting" : "In progress"}
          </Badge>
        </div>

        {/* The number is the largest thing on the card and the call button sits
            beside it, because placing the number and its action together is the
            whole point of this screen. */}
        <div className="row row-between" style={{ marginBottom: "var(--s20)" }}>
          <div className="stack-8">
            <span className="t-micro">Mobile</span>
            <a
              href={`tel:${row.mobile_number.replace(/\s+/g, "")}`}
              className="t-title"
              style={{ color: "var(--navy)" }}
            >
              {row.mobile_number}
            </a>
          </div>
          <Button
            variant="primary"
            onClick={() => {
              window.location.href = `tel:${row.mobile_number.replace(/\s+/g, "")}`;
            }}
          >
            Call {row.first_name}
          </Button>
        </div>

        <hr className="divider" style={{ marginBottom: "var(--s20)" }} />

        <div className="fact-grid">
          <Fact label="Plan interest">{planOf(row)}</Fact>
          <Fact label="Stage">{row.stage === "application" ? "Application" : "Enquiry"}</Fact>
          <Fact label="Status">{label(row.status)}</Fact>
          <Fact label="Email">{row.email ?? "Not given"}</Fact>
        </div>
      </div>

      {/* Recording an outcome is the one thing this screen cannot yet do. Saying
          so plainly beats disabled buttons with no explanation, and beats
          buttons that look like they work and quietly discard the answer. */}
      <Notice
        tone="warn"
        title="Call outcomes cannot be saved yet"
        detail={
          canEdit
            ? "The API has no endpoint for recording what happened on a call. Until POST /api/admin/enquiries/{id}/outcome exists, note the outcome the way the office does today and it will not be lost."
            : "Your role can view enquiries but not change them."
        }
      />
    </>
  );
}
