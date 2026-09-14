import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui";
import { supabase } from "@/lib/supabase";

/**
 * Staff sign-in.
 *
 * There is deliberately no "create account" link. Accounts are created by an
 * administrator in the Supabase dashboard, and the API separately checks the
 * email against a staff allowlist. Self-service sign-up would let anyone with
 * an email address reach client records.
 */
export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!supabase) {
      setError("Sign-in is not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY.");
      return;
    }

    setBusy(true);
    setError(null);

    const { error: signInError } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password,
    });

    if (signInError) {
      // Never distinguish "no such account" from "wrong password": that
      // difference tells an attacker which addresses are real.
      setError("Those details were not recognised.");
      setBusy(false);
      return;
    }
    // On success the session listener in App.tsx takes over.
  };

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={onSubmit}>
        <h1>
          Induduzo <span style={{ color: "var(--gold)" }}>Staff Portal</span>
        </h1>
        <p className="sub">Sign in to manage enquiries.</p>

        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}

        <div className="field">
          <label htmlFor="email">Email address</label>
          <input
            id="email"
                        type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
                        type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        <Button variant="primary" type="submit" block loading={busy} loadingLabel="Signing in…">
          Sign in
        </Button>

        <p className="t-small muted" style={{ marginTop: "var(--s16)", marginBottom: 0 }}>
          This system contains personal information. Access is logged. Do not
          share your login.
        </p>
      </form>
    </div>
  );
}
