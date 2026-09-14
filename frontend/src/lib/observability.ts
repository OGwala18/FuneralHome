import * as Sentry from "@sentry/react";

/**
 * Browser error tracking, with personal data stripped before it is sent.
 *
 * The public site collects an applicant's name, mobile, email, ID number and
 * address. Sentry's defaults would capture much of that through breadcrumbs
 * (every input event, every URL) so the scrubbing here mirrors the server's:
 * the shape of an error is useful, the contents of a person's form are not.
 *
 * Inert unless VITE_SENTRY_DSN is set, so local development stays quiet.
 */

const REDACTED = "[redacted]";

const PATTERNS: [RegExp, string][] = [
  // Credentials in a URL first, before the narrower rules mangle them.
  [/\b(\w+):\/\/[^:/\s]+:[^@/\s]+@/g, "$1://[credentials]@"],
  [/\b\d{13}\b/g, "[id-number]"],
  [/\b(?:\+?27|0)[6-8]\d{8}\b/g, "[mobile]"],
  [/\b[^@\s]+@[^@\s]+\.[^@\s]{2,}\b/g, "[email]"],
];

const scrubText = (value: string): string =>
  PATTERNS.reduce((acc, [pattern, replacement]) => acc.replace(pattern, replacement), value);

const SENSITIVE_KEYS = [
  "password", "secret", "token", "key", "authorization", "cookie", "session",
  "id_number", "mobile", "phone", "email", "address", "postal",
  "first_name", "surname", "full_name", "next_of_kin", "beneficiary",
  "date_of_birth", "notes",
];

const scrub = (node: unknown, depth = 0): unknown => {
  if (depth > 10) return REDACTED;
  if (typeof node === "string") return scrubText(node);
  if (Array.isArray(node)) return node.map((item) => scrub(item, depth + 1));
  if (node && typeof node === "object") {
    return Object.fromEntries(
      Object.entries(node as Record<string, unknown>).map(([key, value]) => {
        const lowered = key.toLowerCase();
        return SENSITIVE_KEYS.some((marker) => lowered.includes(marker))
          ? [key, REDACTED]
          : [key, scrub(value, depth + 1)];
      }),
    );
  }
  return node;
};

export const initObservability = (appName: "website" | "portal"): boolean => {
  const dsn = import.meta.env.VITE_SENTRY_DSN as string | undefined;
  if (!dsn) return false;

  Sentry.init({
    dsn,
    environment: (import.meta.env.VITE_ENVIRONMENT as string) ?? "development",
    release: (import.meta.env.VITE_RELEASE as string) ?? undefined,
    initialScope: { tags: { app: appName } },

    // Do not attach IP address or user identifiers.
    sendDefaultPii: false,

    tracesSampleRate: 0.1,
    // Session Replay would record the applicant filling in the form, ID number
    // and all. Deliberately not enabled.
    replaysSessionSampleRate: 0,
    replaysOnErrorSampleRate: 0,

    beforeSend(event) {
      try {
        return scrub(event) as typeof event;
      } catch {
        // A scrubber that throws must never let an unscrubbed event through.
        return null;
      }
    },

    beforeBreadcrumb(breadcrumb) {
      // Typing into a field generates a breadcrumb per keystroke; the values
      // are exactly the personal data we are trying not to send.
      if (breadcrumb.category === "ui.input") return null;
      if (breadcrumb.message) breadcrumb.message = scrubText(breadcrumb.message);
      if (breadcrumb.data) breadcrumb.data = scrub(breadcrumb.data) as typeof breadcrumb.data;
      return breadcrumb;
    },
  });

  return true;
};
