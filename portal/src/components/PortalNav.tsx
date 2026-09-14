import type { MouseEvent } from "react";
import type { StaffIdentity } from "@/lib/api";
import { hrefFor, navigate, type Route } from "@/lib/router";
import { Button } from "./ui";

/**
 * The portal's one navigation. Four destinations plus Settings, which is the
 * whole application (Hick: the choice is small enough to read at a glance).
 *
 * Rendered on every signed-in screen so the frame never moves between pages.
 */

const DESTINATIONS: { label: string; route: Route }[] = [
  { label: "Today", route: { name: "today" } },
  { label: "People", route: { name: "people" } },
  { label: "Applications", route: { name: "applications" } },
  { label: "Growth", route: { name: "growth" } },
  { label: "Settings", route: { name: "settings" } },
];

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
            aria-current={active === route.name ? "page" : undefined}
            onClick={(e) => go(e, route)}
          >
            {label}
          </a>
        ))}
      </nav>

      {/* Search lives in People. Sending it there rather than duplicating a
          second search box keeps one way to do the job. */}
      <a
        className="nav-search"
        href={hrefFor({ name: "people" })}
        onClick={(e) => go(e, { name: "people" })}
      >
        <SearchMark />
        <span>Find a person or number</span>
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
