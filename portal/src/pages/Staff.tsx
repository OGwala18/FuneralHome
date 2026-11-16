import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  changeStaffRole,
  fetchStaff,
  inviteStaff,
  setStaffActive,
  setStaffMobile,
  type StaffAdded,
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

type AddedNotice = { tone: "success" | "warn"; title: string; detail: string };

/**
 * What to tell the owner after adding someone. The portal signs in with email
 * and password only, and nothing here sets a password from an invitation link,
 * so the owner usually has to create the sign-in in Supabase by hand. Say that
 * plainly rather than leave them waiting for an email that was never sent.
 */
const addedNotice = (member: StaffAdded): AddedNotice =>
  member.invite_sent
    ? {
        tone: "success",
        title: "Added, and invited",
        detail:
          `Supabase has emailed ${member.email} an invitation. The portal can't set ` +
          `a password from that email yet, so if they can't sign in, delete them under ` +
          `Authentication → Users in Supabase and add them again with a password.`,
      }
    : {
        tone: "warn",
        title: "Added. No invitation email was sent",
        detail:
          `${member.email} is on the staff list, but this server doesn't send ` +
          `invitations. In Supabase, go to Authentication → Users → Add user → Create ` +
          `new user. Use this same address, choose a password, and tick Auto Confirm ` +
          `User. Then tell them the password in person or by phone.`,
      };

/** "+27825550123" reads as "082 555 0123", the way the office writes it. */
const formatMobile = (e164: string) => {
  const local = /^\+27(\d{2})(\d{3})(\d{4})$/.exec(e164);
  return local ? `0${local[1]} ${local[2]} ${local[3]}` : e164;
};

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
  const [notice, setNotice] = useState<AddedNotice | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [mobile, setMobile] = useState("");
  const [role, setRole] = useState<StaffRole>("viewer");
  const [inviting, setInviting] = useState(false);

  // The one row whose cell number is open for editing, and what is typed in it.
  const [editingMobile, setEditingMobile] = useState<string | null>(null);
  const [mobileDraft, setMobileDraft] = useState("");

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
        mobile: mobile.trim() || undefined,
        role,
      });
      setEmail("");
      setFullName("");
      setMobile("");
      setRole("viewer");
      setNotice(addedNotice(created));
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

  const startMobileEdit = (member: StaffMember) => {
    setEditingMobile(member.id);
    setMobileDraft(member.mobile ? formatMobile(member.mobile) : "");
    setError(null);
    setNotice(null);
  };

  const onSaveMobile = async (member: StaffMember, event: FormEvent) => {
    event.preventDefault();
    setBusyId(member.id);
    setError(null);
    try {
      await setStaffMobile(member.id, mobileDraft.trim() || null);
      setEditingMobile(null);
      await load();
    } catch (err) {
      // The draft stays open, so a mistyped number can be corrected.
      setError(err instanceof ApiError ? err.message : "Could not save that number.");
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
      {notice && <Notice tone={notice.tone} title={notice.title} detail={notice.detail} />}

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
            <div className="grow" style={{ minWidth: 180 }}>
              <Field
                label="Cell number"
                type="tel"
                value={mobile}
                onChange={setMobile}
                placeholder="082 123 4567"
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
                  <th>Cell</th>
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
                        {editingMobile === m.id ? (
                          <form
                            className="row"
                            style={{ gap: "var(--s8)", flexWrap: "nowrap" }}
                            onSubmit={(e) => void onSaveMobile(m, e)}
                          >
                            <input
                              aria-label={`Cell number for ${m.email}`}
                              type="tel"
                              value={mobileDraft}
                              placeholder="082 123 4567"
                              autoComplete="off"
                              autoFocus
                              style={{ width: "9.5rem" }}
                              onChange={(e) => setMobileDraft(e.target.value)}
                            />
                            <Button small variant="primary" type="submit" loading={busyId === m.id}
                              loadingLabel="Saving…">
                              Save
                            </Button>
                            <Button small type="button" disabled={busyId === m.id}
                              onClick={() => setEditingMobile(null)}>
                              Cancel
                            </Button>
                          </form>
                        ) : (
                          <div className="row" style={{ gap: "var(--s8)", flexWrap: "nowrap" }}>
                            {m.mobile ? (
                              <a href={`tel:${m.mobile}`}>{formatMobile(m.mobile)}</a>
                            ) : (
                              <span className="muted">None</span>
                            )}
                            <Button small disabled={busyId === m.id}
                              aria-label={`${m.mobile ? "Change" : "Add"} cell number for ${m.email}`}
                              onClick={() => startMobileEdit(m)}>
                              {m.mobile ? "Change" : "Add"}
                            </Button>
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
