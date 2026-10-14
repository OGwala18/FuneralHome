import { useMemo } from "react";
import { area, formatDate, fullName, label, planOf } from "@/lib/derive";
import { navigate } from "@/lib/router";
import { useEnquiries } from "@/lib/useEnquiries";
import { Badge, Button, Empty, Notice, Skeleton } from "@/components/ui";

/**
 * People who went past the contact form and started a real application.
 *
 * These are the enquiries closest to becoming policies, which is why they get
 * their own destination rather than a filter chip on People. Serial position:
 * the most valuable list is one click from anywhere, not buried in a dropdown.
 */

export default function Applications() {
  const { rows, loading, error, reload } = useEnquiries({
    sort: "created_at",
    descending: true,
    limit: 200,
  });

  // The list endpoint filters by status, not stage, so the stage split happens
  // here. One request serves both the count and the table.
  const applications = useMemo(() => rows.filter((r) => r.stage === "application"), [rows]);

  const awaiting = useMemo(
    () => applications.filter((r) => r.status === "awaiting_payment").length,
    [applications],
  );

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-text">
          <h1 className="t-heading">Applications</h1>
          <p className="muted">
            {applications.length === 0
              ? "Nobody has completed an application yet."
              : `${applications.length} ${applications.length === 1 ? "person has" : "people have"} completed the full form.`}
          </p>
        </div>
      </div>

      {error && (
        <div style={{ marginBottom: "var(--s16)" }}>
          <Notice
            tone="error"
            title="Could not load applications."
            detail={error}
            action={
              <Button small onClick={() => void reload()}>
                Try again
              </Button>
            }
          />
        </div>
      )}

      {awaiting > 0 && (
        <div style={{ marginBottom: "var(--s20)" }}>
          <Notice
            tone="warn"
            title={`${awaiting} ${awaiting === 1 ? "application is" : "applications are"} waiting on a first payment`}
            detail="These are the closest to becoming active cover."
          />
        </div>
      )}

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        {loading && rows.length === 0 ? (
          <div style={{ padding: "var(--s24)" }}>
            <Skeleton rows={6} />
          </div>
        ) : applications.length === 0 ? (
          <Empty title="No completed applications yet">
            An enquiry becomes an application when somebody finishes the second stage of the form
            on the website.
          </Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Applicant</th>
                  <th>Mobile</th>
                  <th>Area</th>
                  <th>Plan</th>
                  <th>Status</th>
                  <th>Applied</th>
                </tr>
              </thead>
              <tbody>
                {applications.map((row) => (
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
                      <Badge tone={row.status === "active" ? "success" : "due"}>
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
    </div>
  );
}
