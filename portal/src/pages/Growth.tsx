import { useMemo } from "react";
import { byArea, byPlan, conversion, perDay, type Tally } from "@/lib/derive";
import { useEnquiries } from "@/lib/useEnquiries";
import { Button, Empty, Notice, Skeleton } from "@/components/ui";

/**
 * Where enquiries are coming from.
 *
 * Every figure here is counted from the enquiries this page actually loaded.
 * There is no metrics endpoint, so rather than invent one the page states its
 * own window plainly. A funeral business making decisions off a made-up number
 * is worse than no chart at all.
 */

const WINDOW = 200;

export default function Growth() {
  const { page, rows, loading, error, reload } = useEnquiries({
    sort: "created_at",
    descending: true,
    limit: WINDOW,
  });

  const days = useMemo(() => perDay(rows, 30), [rows]);
  const plans = useMemo(() => byPlan(rows), [rows]);
  const areas = useMemo(() => byArea(rows).slice(0, 6), [rows]);
  const convert = useMemo(() => conversion(rows), [rows]);

  const last30 = useMemo(() => days.reduce((sum, d) => sum + d.count, 0), [days]);
  const busiest = useMemo(() => Math.max(0, ...days.map((d) => d.count)), [days]);

  // A full-height bar should mean a busy day. At this office's volume the peak
  // is often one or two, and scaling to that would draw every ordinary day at
  // 100% and read as a spike. Holding the axis at a floor of four keeps the
  // shape honest without inventing anything.
  const scale = Math.max(4, busiest);

  if (loading && rows.length === 0) {
    return (
      <div className="page">
        <div className="page-head">
          <div className="page-head-text">
            <h1 className="t-heading">Growth</h1>
          </div>
        </div>
        <div className="card">
          <Skeleton rows={6} />
        </div>
      </div>
    );
  }

  const total = page?.total ?? rows.length;
  const partial = total > rows.length;

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-text">
          <h1 className="t-heading">Growth</h1>
          <p className="muted">
            Counted from the {rows.length} most recent enquiries
            {partial ? ` of ${total} in total` : ""}. Nothing here is an estimate.
          </p>
        </div>
      </div>

      {error && (
        <div style={{ marginBottom: "var(--s16)" }}>
          <Notice
            tone="error"
            title="Could not load the figures."
            detail={error}
            action={
              <Button small onClick={() => void reload()}>
                Try again
              </Button>
            }
          />
        </div>
      )}

      {rows.length === 0 ? (
        <div className="card">
          <Empty title="Nothing to report yet">
            Once people start registering on the website, this is where the pattern shows up.
          </Empty>
        </div>
      ) : (
        <div className="stack" style={{ gap: "var(--s24)" }}>
          <div className="metrics">
            <div className="card">
              <span className="t-micro">Enquiries, last 30 days</span>
              <div className="metric-value">{last30}</div>
            </div>
            <div className="card">
              <span className="t-micro">Completed applications</span>
              <div className="metric-value">{convert.applications}</div>
            </div>
            <div className="card">
              <span className="t-micro">Enquiry to application</span>
              <div className="metric-value">{convert.percent}%</div>
              <span className="t-small muted">
                {convert.applications} of {convert.leads} loaded
              </span>
            </div>
          </div>

          <section className="card">
            <div className="card-head">
              <h2 className="t-section">Enquiries per day</h2>
              <span className="t-small muted">
                Busiest day: {busiest} · scale to {scale}
              </span>
            </div>
            <div className="columns" role="img" aria-label={`${last30} enquiries over the last 30 days, busiest day ${busiest}`}>
              {days.map((d) => (
                <div
                  className="column"
                  key={d.day}
                  title={`${d.day}: ${d.count} ${d.count === 1 ? "enquiry" : "enquiries"}`}
                >
                  <i style={{ height: `${(d.count / scale) * 100}%` }} />
                </div>
              ))}
            </div>
            <div className="row row-between" style={{ marginTop: "var(--s8)" }}>
              <span className="t-small muted">{days[0]?.day}</span>
              <span className="t-small muted">Today</span>
            </div>
          </section>

          <div className="split">
            <BarCard title="Plan interest" rows={plans} total={rows.length} />
            <BarCard title="Where people are" rows={areas} total={rows.length} />
          </div>

          <Notice
            title="These are counts, not a report"
            detail="The portal has no metrics endpoint, so it totals the enquiries it loaded. For a figure covering all time, query the database directly."
          />
        </div>
      )}
    </div>
  );
}

function BarCard({ title, rows, total }: { title: string; rows: Tally[]; total: number }) {
  const top = Math.max(1, ...rows.map((r) => r.count));

  return (
    <section className="card">
      <div className="card-head">
        <h2 className="t-section">{title}</h2>
      </div>
      {rows.length === 0 ? (
        <p className="t-small muted" style={{ margin: 0 }}>
          Not recorded on these enquiries.
        </p>
      ) : (
        <div className="stack-8">
          {rows.map((row) => (
            <div className="bar-row" key={row.key}>
              <span className="t-small">{row.label}</span>
              <span className="bar">
                <i style={{ width: `${(row.count / top) * 100}%` }} />
              </span>
              <span className="bar-count">{row.count}</span>
            </div>
          ))}
          <span className="t-small muted">
            {rows.reduce((s, r) => s + r.count, 0)} of {total} enquiries have this recorded
          </span>
        </div>
      )}
    </section>
  );
}
