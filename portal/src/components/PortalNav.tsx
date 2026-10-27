import { useEffect, useState, type MouseEvent } from "react";
import { fetchWhatsAppSummary, type StaffIdentity, type WhatsAppSummary } from "@/lib/api";
import { hrefFor, navigate, type Route } from "@/lib/router";
import { Button } from "./ui";

/**
 * The portal's one navigation, shared by all signed-in screens.
 *
 * Rendered on every signed-in screen so the frame never moves between pages.
 */

const DESTINATIONS: { label: string; route: Route }[] = [
  { label: "Today", route: { name: "today" } },
  { label: "Members", route: { name: "members" } },
  { label: "Policies", route: { name: "policies" } },
  { label: "Payments", route: { name: "payments" } },
  { label: "Enquiries", route: { name: "people" } },
  { label: "Applications", route: { name: "applications" } },
  { label: "Growth", route: { name: "growth" } },
  { label: "Settings", route: { name: "settings" } },
];

/** A detail page lights up the list it belongs to. */
const PARENT: Partial<Record<Route["name"], Route["name"]>> = {
  member: "members",
  enrol: "members",
  person: "people",
  policy: "policies",
  whatsapp: "growth",
};

// How often the nav asks whether a WhatsApp family is waiting for a person.
const WHATSAPP_POLL_MS = 60_000;

/** Families waiting for a person on WhatsApp. Counts only, so polling it
 *  writes nothing to the audit trail. A failure just hides the badge. */
function useWhatsAppWaiting(): WhatsAppSummary | null {
  const [summary, setSummary] = useState<WhatsAppSummary | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      if (document.visibilityState === "hidden") return;
      fetchWhatsAppSummary()
        .then((next) => { if (!cancelled) setSummary(next); })
        .catch(() => { if (!cancelled) setSummary(null); });
    };
    load();
    const timer = window.setInterval(load, WHATSAPP_POLL_MS);
    document.addEventListener("visibilitychange", load);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", load);
    };
  }, []);

  return summary;
}

const LeafMark = () => (
  <svg
    className="brand-mark"
    width="30"
    height="30"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    <path d="M20 3C9 2 3 7 4 14s12 8 15-1c1-3 1-7 1-10zM4 21 16 7" />
  </svg>
);

const SearchMark = () => (
  <svg
    width="20"
    height="20"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    strokeLinecap="round"
    aria-hidden="true"
  >
    <circle cx="10.5" cy="10.5" r="6.5" />
    <path d="m16 16 5 5" />
  </svg>
);

const go = (event: MouseEvent, route: Route) => {
  // Left-click navigates in place; modified clicks keep the browser's own
  // behaviour, so "open in new tab" still works on a real link.
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
  event.preventDefault();
  navigate(route);
};

export default function PortalNav({
  active,
  me,
  onSignOut,
}: {
  active: Route["name"];
  me: StaffIdentity;
  onSignOut: () => void;
}) {
  const initials = me.email.slice(0, 2).toUpperCase();
  const waiting = useWhatsAppWaiting();

  return (
    <header className="portal-nav">
      <a className="brand" href="/" onClick={(e) => go(e, { name: "today" })}>
        <LeafMark />
        <span className="brand-words">
          <span className="brand-name">induduzo</span>
          <span className="brand-sub">Funeral home · Staff portal</span>
        </span>
      </a>

      <nav className="nav-links" aria-label="Portal">
        {DESTINATIONS.map(({ label, route }) => (
          <a
            key={label}
            className="nav-link"
            href={hrefFor(route)}
            aria-current={active === route.name || PARENT[active] === route.name ? "page" : undefined}
            onClick={(e) => go(e, route)}
          >
            {label}
            {route.name === "growth" && waiting && waiting.open > 0 && (
              <span
                className={`nav-badge${waiting.urgent > 0 ? " nav-badge-urgent" : ""}`}
                aria-label={`${waiting.open} WhatsApp ${waiting.open === 1 ? "family" : "families"} waiting for a person`}
                title="WhatsApp: families waiting for a person"
              >
                {waiting.open}
              </span>
            )}
          </a>
        ))}
      </nav>

      {/* Search lives in Members. Sending it there rather than duplicating a
          second search box keeps one way to do the job. */}
      <a
        className="nav-search"
        href={hrefFor({ name: "members" })}
        onClick={(e) => go(e, { name: "members" })}
      >
        <SearchMark />
        <span>Find a member</span>
      </a>

      <div className="nav-me">
        <span className="avatar" aria-hidden="true">
          {initials}
        </span>
        <span className="nav-me-text">
          <span className="nav-me-name">{me.email}</span>
          <span className="nav-me-role">{me.role}</span>
        </span>
        <Button variant="ghost" small onClick={onSignOut} style={{ color: "var(--white)" }}>
          Sign out
        </Button>
      </div>
    </header>
  );
}
