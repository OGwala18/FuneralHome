import { useState, type MouseEvent } from "react";
import type { StaffIdentity } from "@/lib/api";
import { hrefFor, navigate, type SettingsSection } from "@/lib/router";
import { Button, Notice } from "@/components/ui";
import Staff from "./Staff";
import ChangePassword from "@/components/ChangePassword";
import BannerEditor from "@/components/settings/BannerEditor";
import FeedbackSettings from "@/components/settings/FeedbackSettings";
import UserUpload from "@/components/settings/UserUpload";

/**
 * Settings: where the office runs its own system without asking a developer
 * (owner, 26 Nov 2026). Four parts, each with its own address:
 *
 *   Team and access   who can sign in, and their role (owners)
 *   Website settings  the homepage banner and the feedback questionnaire
 *   User upload       adding members to the book from a spreadsheet
 *   Portal settings   the office's details: hours, numbers, addresses
 *
 * Changing your own password is a button beside them all, because it is done
 * once, not every visit (owner, 13 Nov 2026).
 *
 * The API decides who may change what; hiding a button here is a courtesy.
 */

const SECTIONS: { id: SettingsSection; label: string; title: string }[] = [
  { id: "team", label: "Team and access", title: "Team and access" },
  { id: "website", label: "Website settings", title: "Website settings" },
  { id: "uploads", label: "User upload", title: "User upload" },
  { id: "portal", label: "Portal settings", title: "Portal settings" },
];

export default function Settings({ me, section = "team" }: { me: StaffIdentity; section?: SettingsSection }) {
  const isOwner = me.role === "owner";
  const [changing, setChanging] = useState(false);
  const [changed, setChanged] = useState(false);
  const active = SECTIONS.find((s) => s.id === section) ?? SECTIONS[0];

  const go = (event: MouseEvent, id: SettingsSection) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    navigate({ name: "settings", section: id });
  };

  return (
    <div className="page">
      <div className="page-head">
        <div className="page-head-text">
          <h1 className="t-heading">{active.title}</h1>
          <nav className="settings-sections" aria-label="Settings">
            {SECTIONS.map((s) => (
              <a
                key={s.id}
                href={hrefFor({ name: "settings", section: s.id })}
                className={`btn btn-small${s.id === active.id ? " btn-selected" : ""}`}
                aria-current={s.id === active.id ? "page" : undefined}
                onClick={(e) => go(e, s.id)}
              >
                {s.label}
              </a>
            ))}
          </nav>
          <p className="muted">
            Signed in as <strong>{me.email}</strong> ({me.role}).
            {active.id === "team" && isOwner && " Removing access here stops the API serving that person, immediately."}
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

        {active.id === "team" && (isOwner ? (
          <Staff myEmail={me.email} />
        ) : (
          <Notice
            title="Only owners manage staff"
            detail="Ask an owner if somebody needs access, or if your own role should change."
          />
        ))}

        {active.id === "website" && (
          <>
            <BannerEditor />
            <FeedbackSettings />
          </>
        )}

        {active.id === "uploads" && <UserUpload canEdit={me.role === "admin" || isOwner} />}

        {active.id === "portal" && (
          <Notice
            title="Office details are being built"
            detail="This is where owners will change the office hours, phone numbers and branch addresses that the website and the WhatsApp replies use, without a developer."
          />
        )}
      </div>
    </div>
  );
}
