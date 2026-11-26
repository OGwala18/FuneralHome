/**
 * What the website reads from the API besides the registration form: the
 * homepage banner staff set in the portal, and the private feedback
 * questionnaire.
 */

import { useEffect, useState } from "react";

export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export class SiteError extends Error {
  readonly status: number;
  readonly fieldErrors: Record<string, string>;
  constructor(message: string, status: number, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.name = "SiteError";
    this.status = status;
    this.fieldErrors = fieldErrors;
  }
}

const call = async <T,>(path: string, init: RequestInit = {}, signal?: AbortSignal): Promise<T> => {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      signal,
      headers: init.body ? { "Content-Type": "application/json" } : undefined,
    });
  } catch {
    throw new SiteError("We could not reach our system just now.", 0);
  }
  if (!response.ok) {
    let message = "Something went wrong on our side. Please try again.";
    let fieldErrors: Record<string, string> = {};
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") message = body.detail;
      if (body?.field_errors && typeof body.field_errors === "object") fieldErrors = body.field_errors;
    } catch {
      /* keep the generic message */
    }
    throw new SiteError(message, response.status, fieldErrors);
  }
  return (await response.json()) as T;
};

// ---------------------------------------------------------------------------
// Homepage banner
// ---------------------------------------------------------------------------

export interface SiteBanner {
  headline_en: string | null;
  headline_zu: string | null;
  message_en: string | null;
  message_zu: string | null;
  /** Relative to the API. Null: the site's own photo. */
  image_url: string | null;
  updated_at: string | null;
}

const BANNER_KEY = "induduzo-banner";
// How long the hero waits for the API before showing the site's own words. A
// first visit on a slow phone should never stare at an empty banner.
const BANNER_WAIT_MS = 1200;

const readCachedBanner = (): SiteBanner | null => {
  try {
    const raw = localStorage.getItem(BANNER_KEY);
    return raw ? (JSON.parse(raw) as SiteBanner) : null;
  } catch {
    return null;
  }
};

/** The photo's full address, or null for the site's own. */
export const bannerImageUrl = (banner: SiteBanner | null): string | null =>
  banner?.image_url ? `${API_BASE}${banner.image_url}` : null;

/**
 * The banner staff set in the portal.
 *
 * The last one seen is kept in this browser, so a returning visitor sees it at
 * once. Otherwise the hero holds its words back for up to 1.2 seconds while the
 * API answers, rather than flashing the standard words and then swapping them.
 * If the API is down, the site's own banner shows: it never depends on the API.
 */
export const useSiteBanner = (): { banner: SiteBanner | null; ready: boolean } => {
  const [banner, setBanner] = useState<SiteBanner | null>(readCachedBanner);
  const [ready, setReady] = useState<boolean>(() => readCachedBanner() !== null);

  useEffect(() => {
    const controller = new AbortController();
    const giveUp = window.setTimeout(() => setReady(true), BANNER_WAIT_MS);
    call<SiteBanner>("/api/site/banner", {}, controller.signal)
      .then((next) => {
        setBanner(next);
        try {
          localStorage.setItem(BANNER_KEY, JSON.stringify(next));
        } catch {
          /* private browsing: just not remembered */
        }
      })
      .catch(() => {
        /* the site's own banner stands */
      })
      .finally(() => {
        window.clearTimeout(giveUp);
        if (!controller.signal.aborted) setReady(true);
      });
    return () => {
      window.clearTimeout(giveUp);
      controller.abort();
    };
  }, []);

  return { banner, ready };
};

// ---------------------------------------------------------------------------
// The private feedback questionnaire
// ---------------------------------------------------------------------------

export type QuestionKind = "text" | "yes_no" | "scale";

export interface FeedbackQuestion {
  id: string;
  kind: QuestionKind;
  text_en: string;
  text_zu: string | null;
}

export interface FeedbackAnswers {
  first_name: string;
  surname: string;
  mobile: string;
  answers: { id: string; answer: string }[];
  contact_consent: boolean;
  source: "qr" | "link";
  language: "en" | "zu";
  website: string;
}

export const fetchQuestionnaire = (code: string) =>
  call<{ questions: FeedbackQuestion[] }>(`/api/feedback/${encodeURIComponent(code)}`);

export const sendFeedback = (code: string, body: FeedbackAnswers) =>
  call<{ id: string }>(`/api/feedback/${encodeURIComponent(code)}/responses`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const sendRating = (responseId: string, rating: number, comment: string) =>
  call<{ ok: boolean }>(`/api/feedback/responses/${encodeURIComponent(responseId)}/rating`, {
    method: "POST",
    body: JSON.stringify({ rating, comment: comment.trim() || null }),
  });
