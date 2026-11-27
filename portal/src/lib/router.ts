import { useEffect, useState } from "react";

/**
 * A ~40 line router instead of a dependency.
 *
 * The portal deliberately keeps its dependency list tiny (see ARCHITECTURE.md
 * §4a), and this app has six destinations and one parameterised route. React
 * Router would be more to keep current than it would save.
 *
 * Real URLs rather than component state, because staff expect the browser to
 * behave like a browser: a person's record can be bookmarked and sent to a
 * colleague, and Back goes back. That is Jakob's Law applied to navigation.
 */

export type Route =
  | { name: "today" }
  | { name: "people" }
  | { name: "person"; id: string }
  | { name: "members" }
  | { name: "member"; id: string }
  /** Enrol a new member. With an enquiry id, the form starts from that enquiry. */
  | { name: "enrol"; enquiryId?: string }
  | { name: "policies" }
  /** `addLives` opens the dependant form straight away, as it is after enrolment. */
  | { name: "policy"; id: string; addLives?: boolean }
  /** Correct the policy's main member: the enrolment form, with what identifies the policy locked. */
  | { name: "editMember"; id: string }
  /** Move the policy to another plan, option or frequency. Same family, same number. */
  | { name: "changePlan"; id: string }
  | { name: "payments" }
  | { name: "applications" }
  | { name: "growth" }
  /** Families who asked the WhatsApp menu for a person. Lives under Growth. */
  | { name: "whatsapp"; id?: string }
  /** The live website's visitors and clicks, from Plausible. Owner only. */
  | { name: "analytics" }
  /** Settings has four parts, each its own address so it can be bookmarked. */
  | { name: "settings"; section?: SettingsSection };

export type SettingsSection = "team" | "website" | "uploads" | "portal";
const SETTINGS_SECTIONS: SettingsSection[] = ["team", "website", "uploads", "portal"];

const parse = (pathname: string, search: string): Route => {
  const parts = pathname.replace(/^\/+|\/+$/g, "").split("/").filter(Boolean);
  const query = new URLSearchParams(search);
  if (parts.length === 0) return { name: "today" };

  switch (parts[0]) {
    case "people":
      return parts[1] ? { name: "person", id: decodeURIComponent(parts[1]) } : { name: "people" };
    case "members":
      if (parts[1] === "new") {
        return { name: "enrol", enquiryId: query.get("enquiry") ?? undefined };
      }
      return parts[1] ? { name: "member", id: decodeURIComponent(parts[1]) } : { name: "members" };
    case "policies":
      if (parts[1] && parts[2] === "edit") return { name: "editMember", id: decodeURIComponent(parts[1]) };
      if (parts[1] && parts[2] === "plan") return { name: "changePlan", id: decodeURIComponent(parts[1]) };
      return parts[1]
        ? { name: "policy", id: decodeURIComponent(parts[1]), addLives: query.has("add") }
        : { name: "policies" };
    case "payments":
      return { name: "payments" };
    case "applications":
      return { name: "applications" };
    case "growth":
      if (parts[1] === "whatsapp") {
        return { name: "whatsapp", id: parts[2] ? decodeURIComponent(parts[2]) : undefined };
      }
      return { name: "growth" };
    case "analytics":
      return { name: "analytics" };
    case "settings": {
      const section = SETTINGS_SECTIONS.find((name) => name === parts[1]);
      return section ? { name: "settings", section } : { name: "settings" };
    }
    default:
      // Unknown path lands on Today rather than a dead end (Peak-End: a flow
      // never terminates on an apology).
      return { name: "today" };
  }
};

export const hrefFor = (route: Route): string => {
  switch (route.name) {
    case "today": return "/";
    case "people": return "/people";
    case "person": return `/people/${encodeURIComponent(route.id)}`;
    case "members": return "/members";
    case "member": return `/members/${encodeURIComponent(route.id)}`;
    case "enrol":
      return route.enquiryId
        ? `/members/new?enquiry=${encodeURIComponent(route.enquiryId)}` : "/members/new";
    case "policies": return "/policies";
    case "policy":
      return `/policies/${encodeURIComponent(route.id)}${route.addLives ? "?add" : ""}`;
    case "editMember": return `/policies/${encodeURIComponent(route.id)}/edit`;
    case "changePlan": return `/policies/${encodeURIComponent(route.id)}/plan`;
    case "payments": return "/payments";
    case "applications": return "/applications";
    case "growth": return "/growth";
    case "whatsapp":
      return route.id ? `/growth/whatsapp/${encodeURIComponent(route.id)}` : "/growth/whatsapp";
    case "analytics": return "/analytics";
    case "settings":
      return route.section && route.section !== "team" ? `/settings/${route.section}` : "/settings";
  }
};

/** Push a new route without a reload. */
export const navigate = (route: Route) => {
  window.history.pushState({}, "", hrefFor(route));
  window.dispatchEvent(new PopStateEvent("popstate"));
};

export const useRoute = (): Route => {
  const [route, setRoute] = useState<Route>(() =>
    parse(window.location.pathname, window.location.search));

  useEffect(() => {
    const onPop = () => setRoute(parse(window.location.pathname, window.location.search));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  // Every route change starts a new task, so start it at the top.
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [route.name, "id" in route ? route.id : "", "section" in route ? route.section : ""]);

  return route;
};
