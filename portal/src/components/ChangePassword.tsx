import { useState, type FormEvent } from "react";
import { Button, Field, Notice } from "@/components/ui";
import { supabase } from "@/lib/supabase";

/**
 * Change your own password, from inside a signed-in session.
 *
 * Why here and not a reset email: staff sign in as firstname@induduzo.co.za,
 * and most of those addresses have no mailbox, so a reset link would go
 * nowhere. An owner creates the account with a temporary password, tells the
 * person by phone or in person, and they replace it here on first sign-in.
 *
 * Reaching this screen already took the password AND the second step, so the
 * session itself is the proof of identity. Supabase stores the new password;
 * it never passes through our API, and we never log it.
 */

const MIN_LENGTH = 12;

export default function ChangePassword() {
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setDone(false);
    if (next.length < MIN_LENGTH) {
      setError(`Use at least ${MIN_LENGTH} characters.`);
      return;
    }
    if (next !== again) {
      setError("The two passwords do not match.");
      return;
    }
    if (!supabase) {
      setError("Sign-in is not configured.");
      return;
    }

    setBusy(true);
    setError(null);
    const { error: updateError } = await supabase.auth.updateUser({ password: next });
    setBusy(false);

    if (updateError) {
      // Supabase's own wording (too weak, same as the old one, sign in again)
      // is clear and contains no personal data.
      setError(updateError.message || "That password could not be saved. Try another.");
      return;
    }
    setNext("");
    setAgain("");
    setDone(true);
  };

  return (
    <form onSubmit={onSubmit} className="stack" style={{ marginTop: "var(--s16)", maxWidth: 420 }}>
      <h3 className="t-section" style={{ margin: 0 }}>Change your password</h3>
      <p className="t-small muted" style={{ margin: 0 }}>
        If an owner gave you a temporary password, replace it now. Use at least {MIN_LENGTH}{" "}
        characters; a short sentence is easiest to remember.
      </p>
      <Field
        label="New password"
        type="password"
        autoComplete="new-password"
        required
        value={next}
        onChange={setNext}
      />
      <Field
        label="New password again"
        type="password"
        autoComplete="new-password"
        required
        value={again}
        onChange={setAgain}
        error={error ?? undefined}
      />
      {done && <Notice tone="success" title="Password changed" detail="Use it next time you sign in." />}
      <div>
        <Button variant="primary" type="submit" loading={busy} loadingLabel="Saving…">
          Change password
        </Button>
      </div>
    </form>
  );
}
