import { useState, type FormEvent } from "react";
import logo from "@/assets/logo.png";
import { Button } from "@/components/ui";
import {
  ApiError,
  holdResetProof,
  requestTemporaryPassword,
  resetPasswordWithTemporary,
} from "@/lib/api";
import { supabase } from "@/lib/supabase";

/**
 * Staff sign-in, and the way back in for someone who has forgotten their
 * password.
 *
 * There is deliberately no "create account" link. Accounts are created by an
 * administrator in the Supabase dashboard, and the API separately checks the
 * email against a staff allowlist. Self-service sign-up would let anyone with
 * an email address reach client records.
 *
 * "Forgot your password?" (owner's request, 16 Nov 2026): the API emails a
 * temporary password that works once, for 30 minutes. The person types it here
 * as the old password beside a new one of their own, and is signed straight in
 * with the new one; the second step follows as on any sign-in. Asking for one
 * changes nothing until it is used, so the old password keeps working. The
 * email links to /reset-password, which opens this screen at that step.
 */

type Mode = "sign-in" | "forgot" | "reset";

const RESET_PATH = "/reset-password";
const MIN_LENGTH = 12;

const startingMode = (): Mode =>
  window.location.pathname.replace(/\/+$/, "") === RESET_PATH ? "reset" : "sign-in";

/** Leave /reset-password once done, so the signed-in portal opens on Today. */
const leaveResetPath = () => {
  if (window.location.pathname.replace(/\/+$/, "") === RESET_PATH) {
    window.history.replaceState(null, "", "/");
  }
};

const messageOf = (error: unknown) =>
  error instanceof Error && error.message ? error.message : "Something went wrong. Please try again.";

export default function Login() {
  const [mode, setMode] = useState<Mode>(startingMode);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [temporary, setTemporary] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const go = (to: Mode, message: string | null = null) => {
    setMode(to);
    setError(null);
    setNotice(message);
    setPassword("");
    if (to !== "reset") {
      setTemporary("");
      setNext("");
      setAgain("");
    }
    if (to === "sign-in") leaveResetPath();
  };

  const signIn = async (event: FormEvent) => {
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

  const askForTemporary = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const answer = await requestTemporaryPassword(email.trim());
      go("reset", answer.detail);
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setBusy(false);
    }
  };

  const saveNewPassword = async (event: FormEvent) => {
    event.preventDefault();
    if (next.length < MIN_LENGTH) {
      setError(`Use at least ${MIN_LENGTH} characters for your new password.`);
      return;
    }
    if (next !== again) {
      setError("The two new passwords do not match.");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const saved = await resetPasswordWithTemporary(email.trim(), temporary, next);
      // Lets the sign-in below skip "Confirm it's you": the temporary password
      // already proved this mailbox, which is all the emailed code would prove.
      holdResetProof(saved.second_step_proof);
    } catch (failure) {
      setError(
        failure instanceof ApiError && failure.code === "validation_failed"
          ? "Please fill in every field."
          : messageOf(failure),
      );
      setBusy(false);
      return;
    }

    // Saved. Sign in with the new password straight away.
    leaveResetPath();
    if (supabase) {
      const { error: signInError } = await supabase.auth.signInWithPassword({
        email: email.trim(),
        password: next,
      });
      if (!signInError) return; // App.tsx takes over, second step and all.
    }
    setBusy(false);
    go("sign-in", "Your new password is saved. Sign in with it now.");
  };

  const heading =
    mode === "sign-in" ? "Sign in to manage enquiries."
    : mode === "forgot" ? "Forgot your password? We'll email you a temporary one."
    : "Choose a new password.";

  return (
    <div className="login-wrap">
      <div className="card login-card">
        <img className="login-logo" src={logo} alt="Induduzo Funeral Home" />
        <h1>
          Induduzo <span style={{ color: "var(--gold)" }}>Staff Portal</span>
        </h1>
        <p className="sub">{heading}</p>

        {notice && (
          <div className="notice notice-success login-notice" role="status">
            <span>{notice}</span>
          </div>
        )}
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}

        {mode === "sign-in" && (
          <form onSubmit={signIn}>
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

            <div className="login-links">
              <button type="button" className="link-button" onClick={() => go("forgot")}>
                Forgot your password?
              </button>
            </div>
          </form>
        )}

        {mode === "forgot" && (
          <form onSubmit={askForTemporary}>
            <p className="t-small" style={{ marginTop: 0 }}>
              Type your work email address. If it's on the staff list, we'll email a
              temporary password that works once, for 30 minutes. Your current password
              keeps working until you choose a new one.
            </p>
            <div className="field">
              <label htmlFor="forgot-email">Email address</label>
              <input
                id="forgot-email"
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <Button variant="primary" type="submit" block loading={busy} loadingLabel="Sending…">
              Email me a temporary password
            </Button>

            <div className="login-links">
              <button type="button" className="link-button" onClick={() => go("reset")}>
                I have a temporary password
              </button>
              <button type="button" className="link-button" onClick={() => go("sign-in")}>
                Back to sign in
              </button>
            </div>
          </form>
        )}

        {mode === "reset" && (
          <form onSubmit={saveNewPassword}>
            <p className="t-small" style={{ marginTop: 0 }}>
              Type the temporary password from the email as your old password, then choose
              your own new one: at least {MIN_LENGTH} characters. A short sentence is easiest
              to remember.
            </p>
            <div className="field">
              <label htmlFor="reset-email">Email address</label>
              <input
                id="reset-email"
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="reset-temporary">Temporary password (from the email)</label>
              <input
                id="reset-temporary"
                type="text"
                autoComplete="one-time-code"
                autoCapitalize="characters"
                spellCheck={false}
                placeholder="ABCD-EFGH-JKMN"
                required
                value={temporary}
                onChange={(e) => setTemporary(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="reset-new">New password</label>
              <input
                id="reset-new"
                type="password"
                autoComplete="new-password"
                required
                value={next}
                onChange={(e) => setNext(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="reset-again">New password again</label>
              <input
                id="reset-again"
                type="password"
                autoComplete="new-password"
                required
                value={again}
                onChange={(e) => setAgain(e.target.value)}
              />
            </div>

            <Button variant="primary" type="submit" block loading={busy} loadingLabel="Saving…">
              Save and sign in
            </Button>

            <div className="login-links">
              <button type="button" className="link-button" onClick={() => go("forgot")}>
                Didn't get it? Send another
              </button>
              <button type="button" className="link-button" onClick={() => go("sign-in")}>
                Back to sign in
              </button>
            </div>
          </form>
        )}

        <p className="t-small muted" style={{ marginTop: "var(--s16)", marginBottom: 0 }}>
          This system contains personal information. Access is logged. Do not
          share your login.
        </p>
      </div>
    </div>
  );
}
