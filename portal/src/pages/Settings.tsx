import { useState } from "react";
import type { StaffIdentity } from "@/lib/api";
import { Button, Notice } from "@/components/ui";
import Staff from "./Staff";
import ChangePassword from "@/components/ChangePassword";

/**
 * Settings is deliberately thin. The Figma design has screens for office
 * details and integrations; neither has an API behind it, so building them
 * would be drawing a picture of a control that does nothing.
 *
 * What is here is real: who else can get in, and your own password. Team and
 * access leads the page; changing your password is a button beside it that
 * opens a small form, because it is done once, not every visit (owner,
 * 13 Nov 2026).
 */

export default function Settings({ me }: { me: StaffIdentity }) {
  const isOwner = me.role === "owner";
  const [changing, setChanging] = useState(false);
  const [changed, setChanged] = useState(false);

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-text">
          <h1 className="t-heading">{isOwner ? "Team and access" : "Settings"}</h1>
          <p className="muted">
            Signed in as <strong>{me.email}</strong> ({me.role}).
            {isOwner && " Removing access here stops the API serving that person, immediately."}
          </p>
        </div>
        {!changing && (
          <Button aria-expanded={false}
            onClick={() => { setChanging(true); setChanged(false); }}>
            Change password
          </Button>
        )}
      </div>

      <div className="stack" style={{ gap: "var(--s24)" }}>
        {changed && (
          <Notice tone="success" title="Password changed" detail="Use it next time you sign in." />
        )}
        {changing && (
          <ChangePassword
            id="change-password"
            onCancel={() => setChanging(false)}
            onChanged={() => { setChanging(false); setChanged(true); }}
          />
        )}

        {isOwner ? (
          <Staff myEmail={me.email} />
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
