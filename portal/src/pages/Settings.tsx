import type { StaffIdentity } from "@/lib/api";
import { Fact, Notice } from "@/components/ui";
import Staff from "./Staff";

/**
 * Settings is deliberately thin. The Figma design has screens for office
 * details and integrations; neither has an API behind it, so building them
 * would be drawing a picture of a control that does nothing.
 *
 * What is here is real: who you are, and who else can get in.
 */

export default function Settings({ me }: { me: StaffIdentity }) {
  const isOwner = me.role === "owner";

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-text">
          <h1 className="t-heading">Settings</h1>
          <p className="muted">Your account, and who else can sign in.</p>
        </div>
      </div>

      <div className="stack" style={{ gap: "var(--s24)" }}>
        <section className="card">
          <div className="card-head">
            <h2 className="t-section">You</h2>
          </div>
          <div className="fact-grid">
            <Fact label="Signed in as">{me.email}</Fact>
            <Fact label="Role">{me.role}</Fact>
          </div>
          <p className="t-small muted" style={{ margin: "var(--s16) 0 0" }}>
            Passwords are managed by Supabase, not here. To change yours, use the reset link on
            the sign-in screen.
          </p>
        </section>

        {isOwner ? (
          <>
            <div className="page-head" style={{ margin: 0 }}>
              <div className="page-head-text">
                <h2 className="t-title">Team and access</h2>
                <p className="muted">
                  Removing access here stops the API serving that person, immediately.
                </p>
              </div>
            </div>
            <Staff myEmail={me.email} />
          </>
        ) : (
          <Notice
            title="Only owners manage staff"
            detail="Ask an owner if somebody needs access, or if your own role should change."
          />
        )}
      </div>
    </div>
  );
}
