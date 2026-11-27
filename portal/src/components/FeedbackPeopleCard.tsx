import { useEffect, useState } from "react";
import { ApiError, fetchFeedbackPeople, type FeedbackPeople } from "@/lib/api";
import { formatDate } from "@/lib/derive";
import { hrefFor, navigate } from "@/lib/router";
import { Empty, Notice, Skeleton } from "@/components/ui";

/**
 * Growth: every family who completed the feedback questionnaire, with the
 * name, surname and cellphone or email they gave (owner, 27 Nov 2026), and
 * how they scored the service (Q2, 1-5) and how likely they are to recommend
 * Induduzo (Q9, 0-10). Their full answers are in Settings > Website settings.
 */

const recommendTone = (n: number) => (n >= 9 ? "promoter" : n >= 7 ? "passive" : "detractor");

export default function FeedbackPeopleCard() {
  const [data, setData] = useState<FeedbackPeople | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchFeedbackPeople()
      .then((next) => { if (!cancelled) setData(next); })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load the questionnaire families.");
      });
    return () => { cancelled = true; };
  }, []);

  const toSettings = { name: "settings", section: "website" } as const;

  return (
    <section className="card stack" style={{ marginBottom: "var(--s24)" }} aria-labelledby="feedback-people">
      <div className="card-head">
        <div className="stack-8">
          <h2 className="t-section" id="feedback-people">Families who answered the feedback questionnaire</h2>
          <p className="t-small muted">
            {data ? `${data.total} ${data.total === 1 ? "family" : "families"}` : "Everyone"} who completed it,
            newest first, with the details they gave so the office can follow up.
            {data && data.anonymous > 0 && ` ${data.anonymous} earlier answers were anonymous.`}
          </p>
        </div>
        <a className="btn btn-small" href={hrefFor(toSettings)}
          onClick={(e) => { e.preventDefault(); navigate(toSettings); }}>
          Answers and results
        </a>
      </div>

      {error && <Notice tone="error" title="Could not load the list." detail={error} />}
      {!data && !error && <Skeleton rows={4} />}
      {data && data.people.length === 0 && (
        <Empty title="Nobody has answered yet">
          Share the questionnaire link or QR code from Settings › Website settings.
        </Empty>
      )}
      {data && data.people.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Name</th>
                <th>Surname</th>
                <th>Cellphone</th>
                <th>Email</th>
                <th>Satisfied (1-5)</th>
                <th>Recommend (0-10)</th>
              </tr>
            </thead>
            <tbody>
              {data.people.map((p) => (
                <tr key={p.id}>
                  <td>{formatDate(p.created_at)}</td>
                  <td className="cell-name">{p.first_name ?? p.name ?? "—"}</td>
                  <td>{p.surname ?? "—"}</td>
                  <td>{p.mobile ? <a href={`tel:${p.mobile}`}>{p.mobile}</a> : <span className="muted">—</span>}</td>
                  <td>{p.email ? <a href={`mailto:${p.email}`}>{p.email}</a> : <span className="muted">—</span>}</td>
                  <td>{p.satisfaction ?? <span className="muted">—</span>}</td>
                  <td>
                    {p.recommend !== null
                      ? <span title={recommendTone(p.recommend)}>{p.recommend}</span>
                      : <span className="muted">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && data.people.length >= 1000 && (
        <p className="t-small muted">Showing the 1,000 most recent.</p>
      )}
    </section>
  );
}
