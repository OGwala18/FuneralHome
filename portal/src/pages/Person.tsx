import { useEffect, useState } from "react";
import { ApiError, fetchEnquiry, type EnquiryDetail } from "@/lib/api";
import { area, formatDate, fullName, label, planLabel, waitingFor } from "@/lib/derive";
import { navigate } from "@/lib/router";
import { Badge, Button, Empty, Fact, Notice, Skeleton } from "@/components/ui";

/**
 * One family's enquiry, and the way into the member book: Add as member opens
 * the enrolment form already filled in from what they typed on the website.
 * Once enrolled, the same button opens their member record instead.
 */

export default function Person({ id, canEdit }: { id: string; canEdit: boolean }) {
  const [row, setRow] = useState<EnquiryDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [missing, setMissing] = useState(false);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setMissing(false);
    fetchEnquiry(id)
      .then((result) => { if (!cancelled) setRow(result); })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && (err.status === 404 || err.status === 422)) setMissing(true);
        else setError(err instanceof ApiError ? err.message : "Could not load this record.");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [id, retry]);

  const back = (
    <Button variant="ghost" onClick={() => navigate({ name: "people" })}>
      Back to enquiries
    </Button>
  );

  if (loading && !row) {
    return (
      <div className="page">
        <div className="page-head">{back}</div>
        <div className="card">
          <Skeleton rows={7} />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page">
        <div className="page-head">{back}</div>
        <Notice
          tone="error"
          title="Could not load this record."
          detail={error}
          action={
            <Button small onClick={() => setRetry((n) => n + 1)}>
              Try again
            </Button>
          }
        />
      </div>
    );
  }

  if (missing || !row) {
    return (
      <div className="page">
        <div className="page-head">{back}</div>
        <div className="card">
          <Empty title="That enquiry is not on record">
            It may have been archived. Search for them by name or reference instead.
          </Empty>
          <div className="row" style={{ justifyContent: "center" }}>
            <Button variant="primary" onClick={() => navigate({ name: "people" })}>
              Search enquiries
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const tel = row.mobile_number.replace(/\s+/g, "");

  return (
    <div className="page">
      <div className="row" style={{ marginBottom: "var(--s16)" }}>
        {back}
        <Badge tone={row.stage === "application" ? "success" : "neutral"}>
          {row.stage === "application" ? "Application" : "Enquiry"}
        </Badge>
        {row.person_id && <Badge tone="success">Member</Badge>}
      </div>

      <div className="page-head">
        <div className="page-head-text">
          <h1 className="t-heading">{fullName(row)}</h1>
          <p className="muted">
            <span className="ref">{row.reference}</span> · {area(row)} · Enquiry received{" "}
            {formatDate(row.created_at)}
          </p>
        </div>
        <div className="row">
          {row.person_id ? (
            <Button onClick={() => navigate({ name: "member", id: row.person_id! })}>
              View member
            </Button>
          ) : canEdit && (
            <Button onClick={() => navigate({ name: "enrol", enquiryId: row.id })}>
              Add as member
            </Button>
          )}
          <Button variant="primary" onClick={() => { window.location.href = `tel:${tel}`; }}>
            Call {row.first_name}
          </Button>
        </div>
      </div>

      <div className="split">
        <div className="stack">
          <section className="card">
            <div className="card-head">
              <h2 className="t-section">Contact</h2>
            </div>
            <div className="fact-grid">
              <Fact label="Mobile">
                <a href={`tel:${tel}`}>{row.mobile_number}</a>
              </Fact>
              <Fact label="Email">
                {row.email ? <a href={`mailto:${row.email}`}>{row.email}</a> : "Not given"}
              </Fact>
              <Fact label="Suburb or town">{row.suburb_or_town ?? "Not given"}</Fact>
              <Fact label="City">{row.city ?? "Not given"}</Fact>
            </div>
          </section>

          <section className="card">
            <div className="card-head">
              <h2 className="t-section">Cover</h2>
            </div>
            <div className="fact-grid">
              <Fact label="Plan interest">{planLabel(row.plan_interest)}</Fact>
              <Fact label="Plan selected">
                {row.plan_selected ? planLabel(row.plan_selected) : "Not chosen yet"}
              </Fact>
              <Fact label="Stage">{label(row.stage)}</Fact>
              <Fact label="Status">{label(row.status)}</Fact>
              {row.number_of_dependants !== null && (
                <Fact label="Dependants listed">{row.number_of_dependants}</Fact>
              )}
            </div>
          </section>
        </div>

        <aside className="stack">
          <section className="card">
            <div className="card-head">
              <h2 className="t-section">A little context</h2>
            </div>
            <div className="stack-8">
              <Fact label="Waiting since">{waitingFor(row.created_at)}</Fact>
              <hr className="divider" />
              <Fact label="Reference">
                <span className="ref">{row.reference}</span>
              </Fact>
            </div>
          </section>

          <section className="card">
            <div className="card-head">
              <h2 className="t-section">History</h2>
            </div>
            <p className="t-small muted" style={{ margin: 0 }}>
              Call history lives in <span className="ref">enquiry_events</span>, which the admin
              API does not expose yet. Once it does, previous conversations belong here, beside
              the number.
            </p>
          </section>
        </aside>
      </div>
    </div>
  );
}
