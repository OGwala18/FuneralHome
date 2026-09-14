import { useEffect, useMemo, useState } from "react";
import type { EnquiryQuery } from "@/lib/api";
import { area, formatDate, fullName, label, planOf } from "@/lib/derive";
import { navigate } from "@/lib/router";
import { useEnquiries } from "@/lib/useEnquiries";
import { Badge, Button, Empty, Notice, Skeleton } from "@/components/ui";

/**
 * Everyone who has ever enquired, searchable. This is the screen staff reach
 * for when somebody phones in and says "I registered last week".
 *
 * Search is the primary control and sits alone at the top; filters come second.
 * Pareto: the common 20% of the job is "find this person by name or number".
 */

const STATUSES = [
  "new",
  "contacted",
  "application_started",
  "application_submitted",
  "awaiting_payment",
  "active",
  "declined",
  "lost",
];

const PAGE_SIZE = 25;

export default function People() {
  const [typed, setTyped] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState<NonNullable<EnquiryQuery["sort"]>>("created_at");
  const [descending, setDescending] = useState(true);
  const [offset, setOffset] = useState(0);

  // Debounced so a search does not fire a request per keystroke. 250ms keeps
  // the result inside the Doherty threshold once the person stops typing.
  useEffect(() => {
    const id = setTimeout(() => {
      setSearch(typed.trim());
      setOffset(0);
    }, 250);
    return () => clearTimeout(id);
  }, [typed]);

  const { page, rows, loading, error, reload } = useEnquiries({
    search: search || undefined,
    status: status || undefined,
    sort,
    descending,
    limit: PAGE_SIZE,
    offset,
  });

  const toggleSort = (field: NonNullable<EnquiryQuery["sort"]>) => {
    if (field === sort) setDescending((d) => !d);
    else {
      setSort(field);
      setDescending(true);
    }
    setOffset(0);
  };

  const mark = (field: string) => (sort === field ? (descending ? " ↓" : " ↑") : "");

  const showing = useMemo(() => {
    if (!page || page.total === 0) return "No people yet";
    const from = page.offset + 1;
    const to = Math.min(page.offset + page.rows.length, page.total);
    return `${from}–${to} of ${page.total}`;
  }, [page]);

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-text">
          <h1 className="t-heading">People</h1>
          <p className="muted">Everyone who has enquired, newest first.</p>
        </div>
      </div>

      <div className="stack" style={{ marginBottom: "var(--s20)" }}>
        <input
          className="search-input"
          type="search"
          placeholder="Search a name, mobile number, email or reference"
          aria-label="Search people"
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          autoFocus
        />
        <div className="row">
          <select
            className="btn"
            aria-label="Filter by status"
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">Every status</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {label(s)}
              </option>
            ))}
          </select>
          {(search || status) && (
            <Button
              variant="ghost"
              onClick={() => {
                setTyped("");
                setStatus("");
                setOffset(0);
              }}
            >
              Clear
            </Button>
          )}
          <span className="grow" />
          <span className="t-small muted">{showing}</span>
        </div>
      </div>

      {error && (
        <div style={{ marginBottom: "var(--s16)" }}>
          <Notice
            tone="error"
            title="Could not load people."
            detail={error}
            action={
              <Button small onClick={() => void reload()}>
                Try again
              </Button>
            }
          />
        </div>
      )}

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        {loading && rows.length === 0 ? (
          <div style={{ padding: "var(--s24)" }}>
            <Skeleton rows={8} />
          </div>
        ) : rows.length === 0 ? (
          <Empty title={search || status ? "Nobody matches that" : "No enquiries yet"}>
            {search || status
              ? "Try a shorter search, or clear the status filter."
              : "People appear here as they register on the website."}
          </Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th className="sortable" onClick={() => toggleSort("surname")}>
                    Name{mark("surname")}
                  </th>
                  <th>Mobile</th>
                  <th>Area</th>
                  <th>Plan</th>
                  <th className="sortable" onClick={() => toggleSort("status")}>
                    Status{mark("status")}
                  </th>
                  <th className="sortable" onClick={() => toggleSort("created_at")}>
                    Received{mark("created_at")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr
                    key={row.id}
                    className="clickable"
                    onClick={() => navigate({ name: "person", id: row.id })}
                  >
                    <td>
                      <div className="cell-name">{fullName(row)}</div>
                      <div className="t-small muted ref">{row.reference}</div>
                    </td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <a href={`tel:${row.mobile_number.replace(/\s+/g, "")}`}>
                        {row.mobile_number}
                      </a>
                    </td>
                    <td className="muted">{area(row)}</td>
                    <td>{planOf(row)}</td>
                    <td>
                      <Badge tone={row.stage === "application" ? "success" : "neutral"}>
                        {label(row.status)}
                      </Badge>
                    </td>
                    <td className="muted">{formatDate(row.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="row row-between" style={{ marginTop: "var(--s16)" }}>
        <span className="t-small muted">{showing}</span>
        <div className="row">
          <Button
            disabled={loading || offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Previous
          </Button>
          <Button
            disabled={loading || !page || offset + PAGE_SIZE >= page.total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  );
}
