import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui";
import {
  ApiError,
  fetchTwoStepStatus,
  sendEmailCode,
  verifyEmailCode,
  type EmailCodeSent,
} from "@/lib/api";

/**
 * "Confirm it's you": the second step after the password.
 *
 * docs/feature-2-staff-two-factor.md §10. Not a URL, a gate state like the
 * login screen. Bit 6 offers the emailed code; the authenticator app, passkeys
 * and recovery codes join this screen in later bits.
 *
 * Nothing is emailed until the person presses the button, and an expired code
 * is never followed by an automatic new one (plan §5).
 */
export default function ConfirmItsYou({
  onDone,
  onSignOut,
}: {
  onDone: () => void;
  onSignOut: () => void;
}) {
  const [hint, setHint] = useState<string | null>(null);
  const [sent, setSent] = useState<EmailCodeSent | null>(null);
  const [code, setCode] = useState("");
  const [trust, setTrust] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [checking, setChecking] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    fetchTwoStepStatus()
      .then((status) => {
        // Already passed (another tab, or a trusted computer): nothing to ask.
        if (status.session_verified || !status.enforced) onDone();
        else setHint(status.email_hint);
      })
      .catch(() => setHint(null));
  }, [onDone]);

  // A once-a-second tick for the countdown and the resend button.
  useEffect(() => {
    if (!sent) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [sent]);

  const expiresAt = sent ? new Date(sent.expires_at).getTime() : 0;
  const resendAt = sent ? new Date(sent.resend_after).getTime() : 0;
  const expired = sent !== null && now >= expiresAt;
  const secondsLeft = Math.max(0, Math.ceil((expiresAt - now) / 1000));
  const resendIn = Math.max(0, Math.ceil((resendAt - now) / 1000));

  const send = async () => {
    setSending(true);
    setError(null);
    try {
      const result = await sendEmailCode();
      setSent(result);
      setHint(result.email_hint);
      setCode("");
      setNow(Date.now());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send a code just now.");
    } finally {
      setSending(false);
    }
  };

  const confirm = async (event: FormEvent) => {
    event.preventDefault();
    if (!sent) return;
    setChecking(true);
    setError(null);
    try {
      await verifyEmailCode(sent.challenge_id, code, trust);
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not check the code just now.");
      setChecking(false);
    }
  };

  const until = sent
    ? new Date(sent.expires_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : "";

  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={confirm}>
        <h1>Confirm it&rsquo;s you</h1>
        <p className="sub">
          Your password was right. To keep members&rsquo; details safe, we also need a code
          from your email.
        </p>

        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}

        {!sent ? (
          <>
            <p className="t-small muted">
              {hint ? <>We&rsquo;ll send a 6-digit code to <strong>{hint}</strong>.</> : null}
            </p>
            <Button type="button" variant="primary" block loading={sending} loadingLabel="Sending…" onClick={send}>
              Email me a code
            </Button>
          </>
        ) : (
          <>
            {expired ? (
              <p className="t-small" role="status">
                This code has expired. Send a new one.
              </p>
            ) : (
              <p className="t-small muted" role="status">
                We sent a code to <strong>{sent.email_hint}</strong>. It expires at {until} (
                {Math.floor(secondsLeft / 60)}:{String(secondsLeft % 60).padStart(2, "0")} left).
              </p>
            )}

            <div className="field">
              <label htmlFor="code">Code from the email</label>
              <input
                id="code"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9 ]*"
                maxLength={7}
                required
                disabled={expired}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/[^0-9]/g, "").slice(0, 6))}
              />
            </div>

            <div className="field">
              <label style={{ display: "flex", gap: "var(--s8)", alignItems: "center" }}>
                <input
                  type="checkbox"
                  checked={trust}
                  onChange={(e) => setTrust(e.target.checked)}
                />
                Trust this computer for 30 days
              </label>
              <span className="field-hint">Only on your own work laptop.</span>
            </div>

            <Button
              variant="primary"
              type="submit"
              block
              loading={checking}
              loadingLabel="Checking…"
              disabled={expired || code.length !== 6}
            >
              Confirm
            </Button>

            <div style={{ marginTop: "var(--s12)" }}>
              <Button type="button" block onClick={send} disabled={resendIn > 0 || sending}>
                {resendIn > 0 ? `Send a new code (${resendIn}s)` : "Send a new code"}
              </Button>
            </div>
          </>
        )}

        <p className="t-small muted" style={{ marginTop: "var(--s16)" }}>
          If you didn&rsquo;t just sign in, someone may know your password. Tell the owner.
        </p>
        <Button type="button" variant="ghost" block onClick={onSignOut}>
          Sign out
        </Button>
      </form>
    </div>
  );
}
