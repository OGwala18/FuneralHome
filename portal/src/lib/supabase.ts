import { createClient } from "@supabase/supabase-js";

/**
 * Supabase is used for AUTHENTICATION ONLY.
 *
 * No client data lives there. Supabase issues a signed token, the portal sends
 * it to our own API, and the API verifies it against Supabase's public key and
 * serves enquiry data from our own Postgres. That keeps client records in one
 * place while never making us responsible for password storage.
 *
 * Both values below are PUBLIC by design — a publishable key identifies the
 * project, it does not grant access. Access is decided by the API's staff
 * allowlist. There is no secret in this bundle.
 */

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string | undefined;

export const authConfigured = Boolean(url && publishableKey);

export const supabase = authConfigured
  ? createClient(url!, publishableKey!, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        // The portal has no OAuth redirect flow, so there is never a token in
        // the URL to detect. Leaving this on would parse the address bar on
        // every load for no reason.
        detectSessionInUrl: false,
      },
    })
  : null;

/** Current access token, or null when signed out. */
export const getAccessToken = async (): Promise<string | null> => {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
};
