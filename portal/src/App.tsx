import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { authConfigured, supabase } from "@/lib/supabase";
import { ApiError, fetchMe, type StaffIdentity } from "@/lib/api";
import { useRoute } from "@/lib/router";
import PortalNav from "@/components/PortalNav";
import { Button } from "@/components/ui";
import Login from "@/pages/Login";
import Today from "@/pages/Today";
import People from "@/pages/People";
import Person from "@/pages/Person";
import Applications from "@/pages/Applications";
import Growth from "@/pages/Growth";
import Settings from "@/pages/Settings";

/**
 * Signed out shows the login; signed in shows the portal.
 *
 * This gate is a CONVENIENCE, not the security boundary. Hiding a destination
 * protects nothing — the API independently verifies the token and re-checks the
 * role on every request, so a hand-crafted call from a viewer still gets a 403.
 */
export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [checking, setChecking] = useState(true);
  const [me, setMe] = useState<StaffIdentity | null>(null);
  const [denied, setDenied] = useState<string | null>(null);
  const route = useRoute();

  useEffect(() => {
    if (!supabase) {
      setChecking(false);
      return;
    }
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setChecking(false);
    });
    const { data: sub } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      if (!next) {
        setMe(null);
        setDenied(null);
      }
    });
    return () => sub.subscription.unsubscribe();
  }, []);

  // Ask the API who we are. A Supabase session alone does not grant access:
  // the account must also be active staff, which only the API can confirm.
  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    fetchMe()
      .then((identity) => {
        if (!cancelled) {
          setMe(identity);
          setDenied(null);
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setMe(null);
        setDenied(
          err instanceof ApiError
            ? err.message
            : "Could not confirm your access. Is the API running?",
        );
      });
    return () => {
      cancelled = true;
    };
  }, [session]);

  if (!authConfigured) {
    return (
      <div className="login-wrap">
        <div className="card login-card">
          <h1>Not configured</h1>
          <p className="sub">
            Copy <code>.env.example</code> to <code>.env</code> and set
            <code> VITE_SUPABASE_URL</code> and
            <code> VITE_SUPABASE_PUBLISHABLE_KEY</code>, then restart.
          </p>
        </div>
      </div>
    );
  }

  if (checking) return <div className="loading">Checking your session…</div>;
  if (!session) return <Login />;

  const signOut = () => void supabase!.auth.signOut();

  // Signed in to Supabase, but the API says this account is not staff.
  if (denied) {
    return (
      <div className="login-wrap">
        <div className="card login-card">
          <h1>No access</h1>
          <p className="sub">{denied}</p>
          <Button variant="primary" block onClick={signOut}>
            Sign out
          </Button>
        </div>
      </div>
    );
  }

  if (!me) return <div className="loading">Checking your access…</div>;

  // `viewer` may read but not change anything. The API enforces this too.
  const canEdit = me.role === "admin" || me.role === "owner";

  return (
    <>
      <PortalNav active={route.name} me={me} onSignOut={signOut} />
      <main>
        {route.name === "today" && <Today canEdit={canEdit} />}
        {route.name === "people" && <People />}
        {route.name === "person" && <Person id={route.id} canEdit={canEdit} />}
        {route.name === "applications" && <Applications />}
        {route.name === "growth" && <Growth />}
        {route.name === "settings" && <Settings me={me} />}
      </main>
    </>
  );
}
