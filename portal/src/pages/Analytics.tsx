import { useEffect, useState } from "react";
import { ApiError, fetchSiteStats, type AnalyticsPeriod, type SiteStats } from "@/lib/api";
import { Button, Empty, Notice, Skeleton } from "@/components/ui";

/**
 * The live website's visitors and clicks, from Plausible. Owner only.
 *
 * Every environment reads the LIVE site, induduzo.co.za: on internal the page
 * is under test but the numbers are real. Plausible counts; it holds no names,
 * phone numbers or ID numbers, so nothing here identifies a family.
 */

const PERIODS: { value: AnalyticsPeriod; label: string; noun: string }[] = [
  { value: "day", label: "Today", noun: "today" },
  { value: "7d", label: "7 days", noun: "in the last 7 days" },
  { value: "28d", label: "28 days", noun: "in the last 28 days" },
  { value: "91d", label: "91 days", noun: "in the last 91 days" },
];

/** The public site's pages, by the names staff use for them. */
const PAGE_NAMES: Record<string, string> = {
  "/": "Home",
  "/about": "About",
  "/services": "Services",
  "/contact": "Contact",
  "/join": "Plans",
  "/register": "Register",
  "/register/details": "Register: details",
  "/gallery": "Gallery",
  "/testimonials": "Testimonials",
  "/founder": "Founder",
};

const pageName = (path: string) => PAGE_NAMES[path] ?? path;

/** The ways a family reaches the office from the site, in the order to read them. */
const CONTACT_GOALS = ["Call", "WhatsApp", "Email", "Contact form", "Enquiry sent", "Application sent"];

const minutes = (seconds: number) => {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
};

const bucketLabel = (bucket: string, period: AnalyticsPeriod) => {
  if (period === "day") return bucket.slice(11, 16) || bucket;
  const date = new Date(`${bucket.slice(0, 10)}T00:00:00`);
  return date.toLocaleDateString("en-ZA", { day: "numeric", month: "short" });
};

export default function Analytics() {
  const [period, setPeriod] = useState<AnalyticsPeriod>("28d");
  const [stats, setStats] = useState<SiteStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchSiteStats(period)
      .then((next) => { if (!cancelled) setStats(next); })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load the figures.");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [period, attempt]);

  const noun = PERIODS.find((p) => p.value === period)?.noun ?? "";
  const current = stats?.period === period ? stats : null;

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-text">
          <h1 className="t-heading">Website analytics</h1>
          <p className="muted">
            Live figures for induduzo.co.za, from Plausible. Counts only: no names or numbers.
          </p>
        </div>
        <div className="row" role="group" aria-label="Period" style={{ gap: "var(--s8)" }}>
          {PERIODS.map((p) => (
            <Button key={p.value} small variant={p.value === period ? "selected" : "secondary"}
              aria-pressed={p.value === period} onClick={() => setPeriod(p.value)}>
              {p.label}
            </Button>
          ))}
        </div>
      </div>

      {error && (
        <div style={{ marginBottom: "var(--s16)" }}>
          <Notice tone="error" title="Could not load the website figures." detail={error}
            action={<Button small onClick={() => setAttempt((n) => n + 1)}>Try again</Button>} />
        </div>
      )}

      {!current ? (
        loading ? <div className="card"><Skeleton rows={8} /></div> : null
      ) : (
        <Figures stats={current} noun={noun} refreshing={loading} />
      )}
    </div>
  );
}

function Figures({ stats, noun, refreshing }: { stats: SiteStats; noun: string; refreshing: boolean }) {
  const { totals, period } = stats;
  const goal = (name: string) => stats.actions.find((a) => a.goal === name);
  const busiest = Math.max(0, ...stats.series.map((b) => b.visitors));
  // Same floor as Growth: at this site's volume, scaling to a peak of one or
  // two would draw every ordinary day as a spike.
  const scale = Math.max(4, busiest);
  const fetched = new Date(stats.fetched_at).toLocaleTimeString("en-ZA", { hour: "2-digit", minute: "2-digit" });

  if (totals.visitors === 0) {
    return (
      <div className="card">
        <Empty title={`No visitors ${noun}`}>
          Plausible has nothing for induduzo.co.za in this period. Try a longer one.
        </Empty>
      </div>
    );
  }

  return (
    <div className="stack" style={{ gap: "var(--s24)", opacity: refreshing ? 0.6 : 1 }}>
      <div className="metrics">
        <Metric label="Visitors" value={totals.visitors} note={`${totals.visits} visits`} />
        <Metric label="Pages viewed" value={totals.pageviews}
          note={`${totals.views_per_visit.toFixed(1)} per visit`} />
        <Metric label="Average visit" value={minutes(totals.visit_duration)} note="minutes : seconds" />
        <Metric label="Left after one page" value={`${Math.round(totals.bounce_rate)}%`} note="bounce rate" />
      </div>

      <section className="card">
        <div className="card-head">
          <h2 className="t-section">Visitors {period === "day" ? "by hour" : "by day"}</h2>
          <span className="t-small muted">Busiest: {busiest} · scale to {scale}</span>
        </div>
        <div className="columns" role="img"
          aria-label={`${totals.visitors} visitors ${noun}, busiest ${period === "day" ? "hour" : "day"} ${busiest}`}>
          {stats.series.map((b) => (
            <div className="column" key={b.bucket}
              title={`${bucketLabel(b.bucket, period)}: ${b.visitors} ${b.visitors === 1 ? "visitor" : "visitors"}, ${b.pageviews} pages`}>
              <i style={{ height: `${(b.visitors / scale) * 100}%` }} />
            </div>
          ))}
        </div>
        <div className="row row-between" style={{ marginTop: "var(--s8)" }}>
          <span className="t-small muted">{stats.series[0] && bucketLabel(stats.series[0].bucket, period)}</span>
          <span className="t-small muted">{period === "day" ? "Now" : "Today"}</span>
        </div>
      </section>

      <section className="card">
        <div className="card-head">
          <h2 className="t-section">How people got in touch</h2>
          <span className="t-small muted">Clicks {noun}</span>
        </div>
        <div className="metrics">
          {CONTACT_GOALS.map((name) => {
            const g = goal(name);
            return (
              <div key={name}>
                <span className="t-micro">{name}</span>
                <div className="metric-value">{g?.events ?? 0}</div>
                <span className="t-small muted">
                  {g ? `${g.visitors} ${g.visitors === 1 ? "person" : "people"} · ${g.conversion_rate}% of visitors` : "None yet"}
                </span>
              </div>
            );
          })}
        </div>
        <p className="t-small muted" style={{ margin: "var(--s16) 0 0" }}>
          Enquiry sent and Application sent stay at zero until the registration API is live.
        </p>
      </section>

      <div className="split split-even">
        <Bars title="Where on the page they clicked" empty="No call, WhatsApp or email clicks yet."
          rows={stats.clicks_by_place.map((c) => ({ key: `${c.goal}|${c.where}`, label: `${c.goal} · ${c.where}`, count: c.events }))} />
        <Bars title="Which page they clicked from" empty="No call, WhatsApp or email clicks yet."
          rows={stats.clicks_by_page.map((c) => ({ key: `${c.goal}|${c.where}`, label: `${c.goal} · ${pageName(c.where)}`, count: c.events }))} />
      </div>

      <section className="card">
        <div className="card-head">
          <h2 className="t-section">The way to an application</h2>
          <span className="t-small muted">People who reached each step {noun}</span>
        </div>
        <div className="stack-8">
          {stats.path.map((step) => (
            <div className="bar-row" key={step.label}>
              <span className="t-small">{step.label}</span>
              <span className="bar"><i style={{ width: `${(step.visitors / Math.max(1, totals.visitors)) * 100}%` }} /></span>
              <span className="bar-count">{step.visitors}</span>
            </div>
          ))}
        </div>
        <p className="t-small muted" style={{ margin: "var(--s12) 0 0" }}>
          Each step counts everyone who reached it, not only those who came through the step before.
        </p>
      </section>

      <section className="card">
        <div className="card-head">
          <h2 className="t-section">Pages</h2>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Page</th><th>Address</th><th style={{ textAlign: "right" }}>Visitors</th><th style={{ textAlign: "right" }}>Views</th></tr>
            </thead>
            <tbody>
              {stats.pages.map((p) => (
                <tr key={p.page}>
                  <td>{pageName(p.page)}</td>
                  <td className="muted">{p.page}</td>
                  <td style={{ textAlign: "right" }}>{p.visitors}</td>
                  <td style={{ textAlign: "right" }}>{p.pageviews}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="split split-even">
        <Bars title="Where visitors came from" empty="No sources recorded."
          rows={stats.sources.map((s) => ({ key: s.label, label: s.label === "Direct / None" ? "Typed it in, or an app" : s.label, count: s.visitors }))} />
        <Bars title="Towns" empty="No towns recorded."
          rows={stats.cities.map((c) => ({ key: c.label, label: c.label, count: c.visitors }))} />
      </div>

      <div className="split split-even">
        <Bars title="Devices" empty="No devices recorded."
          rows={stats.devices.map((d) => ({ key: d.label, label: d.label, count: d.visitors }))} />
        <Bars title="Links out of the site" empty="Nobody has followed a link out yet."
          rows={stats.outbound.map((o) => ({ key: o.url, label: o.url.replace(/^https?:\/\//, ""), count: o.events }))} />
      </div>

      <p className="t-small muted" style={{ margin: 0 }}>
        From Plausible at {fetched}; figures refresh every five minutes.{" "}
        <a href={`https://plausible.io/${encodeURIComponent(stats.site)}`} target="_blank" rel="noopener noreferrer">
          Open the full dashboard in Plausible
        </a>
      </p>
    </div>
  );
}

function Metric({ label, value, note }: { label: string; value: number | string; note: string }) {
  return (
    <div className="card">
      <span className="t-micro">{label}</span>
      <div className="metric-value">{value}</div>
      <span className="t-small muted">{note}</span>
    </div>
  );
}

function Bars({ title, rows, empty }: { title: string; rows: { key: string; label: string; count: number }[]; empty: string }) {
  const top = Math.max(1, ...rows.map((r) => r.count));
  return (
    <section className="card">
      <div className="card-head">
        <h2 className="t-section">{title}</h2>
      </div>
      {rows.length === 0 ? (
        <p className="t-small muted" style={{ margin: 0 }}>{empty}</p>
      ) : (
        <div className="stack-8">
          {rows.map((row) => (
            <div className="bar-row" key={row.key}>
              <span className="t-small">{row.label}</span>
              <span className="bar"><i style={{ width: `${(row.count / top) * 100}%` }} /></span>
              <span className="bar-count">{row.count}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
