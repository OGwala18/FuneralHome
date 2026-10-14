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
  | { name: "payments" }
  | { name: "applications" }
  | { name: "growth" }
  | { name: "settings" };

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
      return parts[1]
        ? { name: "policy", id: decodeURIComponent(parts[1]), addLives: query.has("add") }
        : { name: "policies" };
    case "payments":
      return { name: "payments" };
    case "applications":
      return { name: "applications" };
    case "growth":
      return { name: "growth" };
    case "settings":
      return { name: "settings" };
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
    case "payments": return "/payments";
    case "applications": return "/applications";
    case "growth": return "/growth";
    case "settings": return "/settings";
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
  }, [route.name, "id" in route ? route.id : ""]);

  return route;
};
