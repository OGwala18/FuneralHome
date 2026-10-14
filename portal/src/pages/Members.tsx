import { useEffect, useState } from "react";
import { ApiError, fetchMembers, type MemberPage } from "@/lib/api";
import { navigate } from "@/lib/router";
import { Badge, Button, Empty, Notice, Skeleton } from "@/components/ui";

const PAGE_SIZE = 25;

export default function Members() {
  const [typed, setTyped] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<MemberPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(typed.trim());
      setOffset(0);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [typed]);

  useEffect(() => {
    let cancelled = false;
    setPage(null);
    setLoading(true);
    setError(null);
    fetchMembers({ search, limit: PAGE_SIZE, offset })
      .then((result) => { if (!cancelled) setPage(result); })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "Could not load members.");
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [search, offset, retry]);

  const rows = page?.rows ?? [];
  const showing = loading && !page ? "Loading members…" : page?.total
    ? `${page.offset + 1}–${Math.min(page.offset + rows.length, page.total)} of ${page.total}`
    : "No members yet";

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-text">
          <h1 className="t-heading">Members</h1>
          <p className="muted">People in the imported policy book.</p>
        </div>
      </div>

      <div className="stack" style={{ marginBottom: "var(--s20)" }}>
        <input className="search-input" type="search" aria-label="Search members"
          placeholder="Search name, email or ID number" value={typed}
          onChange={(event) => setTyped(event.target.value)} autoFocus />
        <div className="row">
          {typed && <Button variant="ghost" onClick={() => setTyped("")}>Clear</Button>}
          <span className="grow" />
          <span className="t-small muted">{showing}</span>
        </div>
      </div>

      {error && <Notice tone="error" title="Could not load members." detail={error}
        action={<Button small onClick={() => setRetry((value) => value + 1)}>Try again</Button>} />}

      <div className="card" style={{ padding: 0, overflow: "hidden" }}>
        {loading && !page ? <div style={{ padding: "var(--s24)" }}><Skeleton rows={8} /></div>
          : rows.length === 0 ? <Empty title={search ? "Nobody matches that" : "No members found"}>
              {search ? "Try a shorter search." : "The member book has no records yet."}
            </Empty>
          : <div className="table-wrap">
              <table>
                <thead><tr><th>Name</th><th>Email</th><th>ID check</th></tr></thead>
                <tbody>{rows.map((row) => <tr key={row.id} className="clickable"
                  onClick={() => navigate({ name: "member", id: row.id })}>
                  <td className="cell-name">{row.first_names} {row.surname}</td>
                  <td className="muted">{row.email ?? "Not given"}</td>
                  <td><Badge tone={row.id_number_status === "valid" ? "success" : "neutral"}>
                    {row.id_number_status.replace(/_/g, " ")}</Badge></td>
                </tr>)}</tbody>
              </table>
            </div>}
      </div>

      <div className="row row-between" style={{ marginTop: "var(--s16)" }}>
        <span className="t-small muted">{showing}</span>
        <div className="row">
          <Button disabled={loading || offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</Button>
          <Button disabled={loading || !page || offset + PAGE_SIZE >= page.total}
            onClick={() => setOffset(offset + PAGE_SIZE)}>Next</Button>
        </div>
      </div>
    </div>
  );
}
