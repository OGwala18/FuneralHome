import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  changeStaffRole,
  fetchStaff,
  inviteStaff,
  setStaffActive,
  type StaffMember,
  type StaffRole,
} from "@/lib/api";
import { Badge, Button, Empty, Field, Notice, Skeleton } from "@/components/ui";

/**
 * Staff management. Only reachable by owners, and the API enforces that
 * independently: hiding this screen protects nothing on its own.
 *
 * Behaviour is unchanged from the original; this is the same logic wearing the
 * portal's design system.
 */

const ROLES: { value: StaffRole; label: string; what: string }[] = [
  { value: "viewer", label: "Viewer", what: "Can view enquiries only" },
  { value: "admin", label: "Admin", what: "Can view and edit enquiries" },
  { value: "owner", label: "Owner", what: "Everything, including managing staff" },
];

const formatWhen = (iso: string | null) => {
  if (!iso) return "Never";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-ZA", { day: "2-digit", month: "short", year: "numeric" });
};

export default function Staff({ myEmail }: { myEmail: string }) {
  const [rows, setRows] = useState<StaffMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<StaffRole>("viewer");
  const [inviting, setInviting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows(await fetchStaff());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load staff.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onInvite = async (event: FormEvent) => {
    event.preventDefault();
    setInviting(true);
    setError(null);
    setNotice(null);
    try {
      const created = await inviteStaff({
        email: email.trim(),
        full_name: fullName.trim() || undefined,
        role,
      });
      setEmail("");
      setFullName("");
      setRole("viewer");
      setNotice(
        `${created.email} can now be given access. If they did not receive an ` +
          `invitation email, create their account in Supabase.`,
      );
      await load();
    } catch (err) {
      // The typed values stay on screen, so a rejected address can be corrected
      // rather than retyped.
      setError(err instanceof ApiError ? err.message : "Could not add that person.");
    } finally {
      setInviting(false);
    }
  };

  const onRoleChange = async (member: StaffMember, next: StaffRole) => {
    setBusyId(member.id);
    setError(null);
    setNotice(null);
    try {
      await changeStaffRole(member.id, next);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not change that role.");
      await load(); // resync the dropdown with reality
    } finally {
      setBusyId(null);
    }
  };

  const onToggleActive = async (member: StaffMember) => {
    setBusyId(member.id);
    setError(null);
    setNotice(null);
    try {
      await setStaffActive(member.id, !member.is_active);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update that account.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="stack" style={{ gap: "var(--s24)" }}>
      {error && <Notice tone="error" title="That did not work" detail={error} />}
      {notice && <Notice tone="success" title="Added" detail={notice} />}

      <section className="card">
        <div className="card-head">
          <div className="stack-8">
            <h2 className="t-section">Add someone to the office</h2>
            <span className="t-small muted">
              They can sign in with this address once their account exists.
            </span>
          </div>
        </div>

        <form onSubmit={onInvite}>
          <div className="row" style={{ alignItems: "flex-start", gap: "var(--s16)" }}>
            <div className="grow" style={{ minWidth: 240 }}>
              <Field
                label="Email address"
                type="email"
                required
                value={email}
                onChange={setEmail}
                placeholder="name@induduzo.co.za"
                autoComplete="off"
              />
            </div>
            <div className="grow" style={{ minWidth: 200 }}>
              <Field
                label="Full name"
                value={fullName}
                onChange={setFullName}
                hint="Optional"
                autoComplete="off"
              />
            </div>
            <div className="field" style={{ minWidth: 160 }}>
              <label htmlFor="new-role">Role</label>
              <select
                id="new-role"
                value={role}
                onChange={(e) => setRole(e.target.value as StaffRole)}
              >
                {ROLES.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
              <span className="field-hint">{ROLES.find((r) => r.value === role)?.what}</span>
            </div>
          </div>

          <Button variant="primary" type="submit" loading={inviting} loadingLabel="Adding…">
            Add to the office
          </Button>
        </form>
      </section>

      <section className="card" style={{ padding: 0, overflow: "hidden" }}>
        {loading && rows.length === 0 ? (
          <div style={{ padding: "var(--s24)" }}>
            <Skeleton rows={4} />
          </div>
        ) : rows.length === 0 ? (
          <Empty title="No staff accounts yet">
            Add the first person above. Owners can manage everybody else.
          </Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Person</th>
                  <th>Role</th>
                  <th>Signed in</th>
                  <th>Last seen</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((m) => {
                  const isMe = m.email.toLowerCase() === myEmail.toLowerCase();
                  return (
                    <tr key={m.id} style={{ opacity: m.is_active ? 1 : 0.55 }}>
                      <td>
                        <div className="cell-name">{m.full_name || m.email}</div>
                        {m.full_name && <div className="t-small muted">{m.email}</div>}
                        {isMe && (
                          <div style={{ marginTop: 4 }}>
                            <Badge>You</Badge>
                          </div>
                        )}
                      </td>
                      <td>
                        <select
                          aria-label={`Role for ${m.email}`}
                          className="btn"
                          value={m.role}
                          disabled={busyId === m.id || !m.is_active}
                          onChange={(e) => void onRoleChange(m, e.target.value as StaffRole)}
                        >
                          {ROLES.map((r) => (
                            <option key={r.value} value={r.value}>
                              {r.label}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="muted">{m.has_signed_in ? "Yes" : "Not yet"}</td>
                      <td className="muted">{formatWhen(m.last_seen_at)}</td>
                      <td>
                        <Badge tone={m.is_active ? "success" : "neutral"}>
                          {m.is_active ? "Active" : "Deactivated"}
                        </Badge>
                      </td>
                      <td>
                        <Button
                          small
                          disabled={busyId === m.id || isMe}
                          title={isMe ? "You cannot deactivate your own account" : undefined}
                          onClick={() => void onToggleActive(m)}
                        >
                          {m.is_active ? "Deactivate" : "Reactivate"}
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
