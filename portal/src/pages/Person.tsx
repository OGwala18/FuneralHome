import { area, formatDate, fullName, label, planLabel, waitingFor } from "@/lib/derive";
import { navigate } from "@/lib/router";
import { useEnquiries } from "@/lib/useEnquiries";
import { Badge, Button, Empty, Fact, Notice, Skeleton } from "@/components/ui";

/**
 * One family's record.
 *
 * A caveat worth knowing: the API has no `GET /api/admin/enquiries/{id}`, so
 * this page finds its person inside a page of the list endpoint. That is fine
 * at the office's current volume and honest about its limit below, but the
 * right fix is the single-record route, not a bigger window here.
 */

const LOOKUP_WINDOW = 200;

export default function Person({ id, canEdit }: { id: string; canEdit: boolean }) {
  const { rows, loading, error, reload } = useEnquiries({
    sort: "created_at",
    descending: true,
    limit: LOOKUP_WINDOW,
  });

  const row = rows.find((r) => r.id === id);

  const back = (
    <Button variant="ghost" onClick={() => navigate({ name: "people" })}>
      Back to people
    </Button>
  );

  if (loading && rows.length === 0) {
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
            <Button small onClick={() => void reload()}>
              Try again
            </Button>
          }
        />
      </div>
    );
  }

  if (!row) {
    return (
      <div className="page">
        <div className="page-head">{back}</div>
        <div className="card">
          <Empty title="That record is not in view">
            This page looks for a person inside the most recent {LOOKUP_WINDOW} enquiries,
            because the API has no route for fetching one by id. Search for them by name or
            reference instead.
          </Empty>
          <div className="row" style={{ justifyContent: "center" }}>
            <Button variant="primary" onClick={() => navigate({ name: "people" })}>
              Search people
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
      </div>

      <div className="page-head">
        <div className="page-head-text">
          <h1 className="t-heading">{fullName(row)}</h1>
          <p className="muted">
            <span className="ref">{row.reference}</span> · {area(row)} · Enquiry received{" "}
            {formatDate(row.created_at)}
          </p>
        </div>
        <Button variant="primary" onClick={() => { window.location.href = `tel:${tel}`; }}>
          Call {row.first_name}
        </Button>
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
            </div>
          </section>

          {canEdit && (
            <Notice
              tone="warn"
              title="Editing is not wired up"
              detail="The API exposes no update route for an enquiry, so this record is read-only in the portal. Changes are made the way the office makes them today."
            />
          )}
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
